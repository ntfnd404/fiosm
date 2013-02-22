#!/usr/bin/python
# -*- coding: UTF-8 -*-
from __future__ import division

from copy import copy
import logging
import psycopg2
import ppygis
import psycopg2.extras
import uuid
psycopg2.extras.register_uuid()
import psycopg2.extensions
psycopg2.extensions.register_type(psycopg2.extensions.UNICODE)
psycopg2.extensions.register_type(psycopg2.extensions.UNICODEARRAY)

import mangledb
from config import *
conn=psycopg2.connect(connstr)
conn.autocommit=True
stat_cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

socr_cache={}
#with keys socr#aolev

typ_cond = {'all': '',
    'found': 'EXISTS(SELECT aoguid FROM ' + prefix + pl_aso_tbl + ' WHERE aoguid=f.aoguid)',
    'street': 'EXISTS(SELECT aoguid FROM ' + prefix + way_aso_tbl + ' WHERE aoguid=f.aoguid)',
    'not found': None
         }


def GetAreaList(parentguid,typ,count=False):
    cur_=conn.cursor()
    if typ=='not found':
        type_cond="NOT("+" OR ".join(filter(None,typ_cond.values()))+")"
    elif typ_cond.has_key(typ):
        type_cond=typ_cond[typ]
#    else:
#        return []
    
    if type_cond<>"":
        type_cond=" AND "+type_cond
    what='Count(aoguid)' if count else 'aoguid'
    if parentguid=='' or (parentguid is None):
        cur_.execute("SELECT "+what+" FROM fias_addr_obj f WHERE parentguid is Null"+type_cond)
    else:
        cur_.execute("SELECT "+what+" FROM fias_addr_obj f WHERE parentguid=%s"+type_cond,(parentguid,))
    
    res=cur_.fetchone()
    while res:
        yield res[0]
        res=cur_.fetchone()

def SaveAreaStat(guid,stat):
    if guid==None :
        return
    #psycopg2.extras.wait_select(stat_conn)
    stat['guid']=guid
    if ('all' in stat) and ('found' in stat) and ('street' in stat) and ('all_b' in stat) and ('found_b' in stat):
        stat_cur.execute('DELETE FROM fiosm_stat WHERE aoguid=%s',(guid,))
        stat_cur.execute('''INSERT INTO fiosm_stat (ao_all, found, street, all_b, found_b,aoguid) 
        VALUES (%(all)s , %(found)s , %(street)s , %(all_b)s , %(found_b)s , %(guid)s) ''',stat)

class fias_AO(object):
    def __init__(self,guid,kind=None,osmid=None,parent=None):
        if guid=="":
            guid=None
        self.guid=guid
        self.setkind(kind)
        if osmid:
            self._osmid=osmid
        if parent:
            self._parent=parent
        self._subs={}
        self._stat={}
    
    def calkind(self):
        cur=conn.cursor()
        #'found'
        cur.execute('SELECT osm_admin FROM '+prefix+pl_aso_tbl+' WHERE aoguid=%s',(self.guid,))
        cid=cur.fetchone()
        if cid:
            self._osmid=cid[0]
            self._kind=2
            return 2
        #'street':
        cur.execute('SELECT osm_way FROM '+prefix+way_aso_tbl+' WHERE aoguid=%s',(self.guid,))
        cid=cur.fetchone()
        if cid:
            self._osmid=cid[0]
            self._kind=1
        else:
            self._kind=0
        return self._kind
    
    def getkind(self):
        if self.guid==None:
            return 2    
        if not hasattr(self,'_kind') or self._kind==None:
            return self.calkind()
        return self._kind
    
    def setkind(self,kind):
        if not type(kind) is int:
            if str(kind)=='found':
                self._kind=2
            elif str(kind)=='street':
                self._kind=1
            elif str(kind)=='not found':
                self._kind=0
            else:
                self._kind=None
        else:
            self._kind=kind
            
    def delkind(self):
        del self._kind
        
    kind=property(getkind,setkind,delkind,'''Basic type of object
        0-not found
        1-street
        2-found as area
        ''')
    
    def getFiasData(self):
        cur=conn.cursor()
        if self.guid:
            cur.execute('SELECT parentguid, updatedate, postalcode, code, okato, oktmo, offname, formalname, shortname, aolevel FROM fias_addr_obj WHERE aoguid=%s',(self.guid,))
            firow=cur.fetchone()
        else:
            firow=[None,None,None,None,None,None,None,None,None,None]
        if firow:
            self._parent=firow[0]
            self._fias={}
            self._fias['updatedate']=firow[1]
            self._fias['postalcode']=firow[2]
            self._fias['kladr']=firow[3]
            self._fias['okato']=firow[4]
            self._fias['oktmo']=firow[5]
            self._offname=firow[6]
            self._formalname=firow[7]
            self._shortname=firow[8]
            self._aolevel=firow[9]
            self._is=True
        else:
            self._is=False
        
    @property
    def fias(self):
        if not hasattr(self,'_fias'):
            self.getFiasData()
        return self._fias
    
    @property
    def offname(self):
        if not hasattr(self,'_offname'):
            self.getFiasData()
        return self._offname

    @property
    def formalname(self):
        if not hasattr(self,'_formalname'):
            self.getFiasData()
        return self._formalname

    @property
    def shortname(self):
        if not hasattr(self,'_shortname'):
            self.getFiasData()
        return self._shortname
    
    @property
    def fullname(self):
        key=u"#".join((self._shortname,str(self._aolevel)))
        if key in socr_cache:
            return socr_cache[key]
        cur_=conn.cursor()
        cur_.execute("""SELECT lower(socrname) FROM fias_socr_obj s
        WHERE scname=%s AND level=%s """,(self._shortname,self._aolevel))
        res=cur_.fetchone()
        if res:
            socr_cache[key]=res[0]
            return res[0]
        
    def names(self,formal=True):
        name_=self.formalname if formal else self.offname
        if mangledb.usable and self.kind!=2:
            mangled=mangledb.db.CheckCanonicalForm(self.shortname+" "+name_)
            if mangled:
                yield mangled[0]
        yield self.fullname+" "+name_
        yield name_+" "+self.fullname
        #As AMDmi3 promises
        #yield self.shortname+" "+name_
        #yield name_+" "+self.shortname
        yield name_  
 
    @property
    def parent(self):
        if not hasattr(self,'_parentO'):
            if not hasattr(self,'_parent'):
                self.getFiasData()
            #if self._parent==None:
            #    return self
            self._parentO=fias_AO(self._parent)
        return self._parentO
    
    @property
    def isok(self):
        if self.guid==None:
            return True 
        if not hasattr(self,'_is'):
            self.getFiasData()
        return self._is
    
    def CalcAreaStat(self,typ,force=False):
        if not force and typ in self._stat:
            return
        #elem={}
        if typ in ('all','found','street'):
            if not force and self._subs.has_key(typ):
                self._stat[typ]=len(self._subs[typ])
            elif ('all' in self._stat and self._stat['all']==0) or (self.kind==0 and typ=='found') or (self.kind<2 and typ=='street'):
                self._stat[typ]=0
            else:
                self._stat[typ]=GetAreaList(self.guid,typ,True).next()
        
        elif typ.endswith('_b'):
            cur_=conn.cursor()
            if typ=='all_b':
                if self.guid==None or self.kind==0:
                    self._stat['all_b']=0
                elif force or (not 'all_b' in self._stat):
                    cur_.execute("SELECT count(distinct(houseguid)) FROM fias_house WHERE aoguid=%s",(self.guid,))
                    self._stat['all_b']=cur_.fetchone()[0]
            elif typ=='found_b':
                if self.stat('all_b')==0:
                    self._stat['found_b']=0
                elif not force and 'found_b' in self._subs:
                    self._stat['found_b']=len(self._subs['found_b'])
                elif force or not 'found_b' in self._stat:
                    cur_.execute("SELECT count(distinct(f.houseguid)) FROM fias_house f, "+prefix+bld_aso_tbl+" o WHERE f.aoguid=%s AND f.houseguid=o.aoguid",(self.guid,))
                    self._stat['found_b']=cur_.fetchone()[0]

        elif typ.endswith('_r'):
            res=self.stat(typ[:-2])
            for ao in self.subAO('found'):
                res+=fias_AO(ao).stat(typ)
            for ao in self.subAO('street'):
                res+=fias_AO(ao).stat(typ[:-2])
            for ao in self.subAO('not found'):
                res+=fias_AO(ao).stat(typ[:-2])
    
    def pullstat(self,row):
        '''Pull stat info from row of dictionary-like cursor'''
        self._stat['all']=row.get('ao_all')
        self._stat['found']=row.get('found')
        self._stat['street']=row.get('street')
        self._stat['all_b']=row.get('all_b')
        self._stat['found_b']=row.get('found_b')
        self._stat['all_r']=row.get('all_r')
        self._stat['found_r']=row.get('found_r')
        self._stat['street_r']=row.get('street_r')
        self._stat['all_b_r']=row.get('all_b_r')
        self._stat['found_b_r']=row.get('found_b_r')
        
        
    def stat(self,typ):
        '''Statistic of childs for item'''
        if typ=='not found':
            return self.stat('all')-self.stat('found')-self.stat('street')
        elif typ=='not found_b':
            return self.stat('all_b')-self.stat('found_b')
        if not typ in self._stat:
            if self.guid==None:
                res=None
            else:
                #psycopg2.extras.wait_select(stat_conn)
                stat_cur.execute('SELECT ao_all, found, street, all_b, found_b FROM fiosm_stat WHERE aoguid=%s',(self.guid,))
                #psycopg2.extras.wait_select(stat_conn)
                res=stat_cur.fetchone()
                
            if res!=None:
                self.pullstat(res)
                
            if self._stat.get(typ)==None:                 
                self.CalcAreaStat(typ)
                SaveAreaStat(self.guid,self._stat)
        return self._stat[typ]   
        
    @property
    def name(self):
        '''Name of object as on map'''
        if self.guid==None: 
            return u"Россия"
        if hasattr(self,'_name'):
            return self._name
        
        if True:#hasattr(self,'_osmid'): #speedup on web interface
            cur_=conn.cursor()
            if self.kind==2:
                cur_.execute('SELECT name FROM '+prefix+poly_table+'  WHERE osm_id=%s ',(self.osmid,))
                name=cur_.fetchone()
                if name:
                    self._name=name[0]
            if self.kind==1:
                cur_.execute('SELECT name FROM '+prefix+ways_table+'  WHERE osm_id=%s ',(self.osmid,))
                name=cur_.fetchone()
                if name:
                    self._name=name[0]
        
        if not hasattr(self,'_name'):
            self._name=self.names().next()
        return self._name

    @property
    def osmid(self):
        if not hasattr(self,'_osmid'):
            if hasattr(self,'_kind') and not self._kind:
                return None
            #Do not even try if not found
            if not self.calkind():
                return None
            #and if we have kind other than 'not found' then we 
            #receive osmid while we calculate
        return self._osmid
          
    @property
    def geom(self):
        '''Geometry where buildings can be'''
        if not self.guid:
            return None
        if hasattr(self,'_geom'):
            return self._geom
        cur_=conn.cursor()
        if self.kind==2 and self.osmid<>None:
            cur_.execute("SELECT way FROM "+prefix+poly_table+" WHERE osm_id=%s",(self.osmid,))
            self._geom=cur_.fetchone()[0]
        elif self.kind==1:
            cur_.execute("SELECT St_Buffer(ST_Union(w.way),2000) FROM "+prefix+ways_table+" w, "+prefix+way_aso_tbl+" s WHERE s.osm_way=w.osm_id AND s.aoguid=%s",(self.guid,))
            self._geom=cur_.fetchone()[0]
        else:
            return None
        return self._geom


class fias_AONode(fias_AO):
    def __init__(self, *args, **kwargs):
        if type(args[0]) == fias_AO:
            self = copy(args[0])
            self.__class__ = fias_AONode
        else:
            fias_AO.__init__(self, *args, **kwargs)
        self._subO = {}

    def builds(self, point):
        point_ = 1 if point else 0
        cur_ = conn.cursor()
        cur_.execute("SELECT o.osm_build, o.aoguid FROM fias_house f, " + prefix + bld_aso_tbl + " o WHERE f.houseguid=o.aogiid AND f.aoguid=%s AND o.point=%s", (self.guid, point_))  
        res = {}
        for it in cur_.fetchall():
            res[it[0]] = it[1]
        return res

    def subAO(self, typ, need_stat=True):
        #Voids by kind
        if self.kind != 2 and typ != 'not found':
            return []
        cmpop = ' is ' if self.guid == None else ' = '
        if need_stat:
            stat_join = "LEFT JOIN fiosm_stat s ON f.aoguid=s.aoguid"
            stat_sel = ", s.*"
        else:
            stat_join = ""
            stat_sel = ""
        #make request
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        if typ == 'found':
            osmid = 'osm_admin'
            cur.execute('SELECT f.aoguid, f.formalname, f.shortname, f.aolevel, a.' + osmid + ', o.name' + stat_sel + ' FROM fias_addr_obj f INNER JOIN ' + prefix + pl_aso_tbl + ' a ON f.aoguid=a.aoguid INNER JOIN ' + prefix + poly_table + ' o ON a.' + osmid + '=o.osm_id ' + stat_join + ' WHERE parentguid' + cmpop + '%s', (self.guid,))
            kind = 2
        elif typ == 'street':
            kind = 1
            osmid = 'osm_way'
            cur.execute('SELECT DISTINCT ON(f.aoguid) f.formalname, f.shortname, f.aolevel, a.' + osmid + ', o.name, s.* FROM fias_addr_obj f INNER JOIN ' + prefix + way_aso_tbl + ' a ON f.aoguid=a.aoguid INNER JOIN ' + prefix + ways_table + ' o ON a.' + osmid + '=o.osm_id ' + stat_join + ' WHERE parentguid' + cmpop + '%s', (self.guid,))
        elif typ == 'not found':
            kind = 0
            osmid = None
            cur.execute('SELECT f.aoguid, f.formalname, f.shortname, f.aolevel' + stat_sel + ' FROM fias_addr_obj ' + stat_join + ' WHERE NOT(' + typ_cond['found'] + ' OR ' + typ_cond['street'] + ') AND parentguid' + cmpop + '%s', (self.guid,))
        else:
            return []
        self._subO[typ] = []
        for row in cur.fetchall():
            el = fias_AO(row['aoguid'], kind, row[osmid] if osmid else None, self.guid)
            el._formalname = row['formalname']
            el._shortname = row['shortname']
            el._aolevel = row['aolevel']
            el.pullstat(row)
            if kind:
                el._name = row['name']
            self._subO[typ].append(el)
        return self._subO[typ]

    def subO(self, typ):
        '''List of subelements'''
        if typ in self._subO:
            return self._subO[typ]

        if typ in ('not found', 'found', 'street'):
            return self.subAO(typ)
        if typ == 'all':
            res = []
            res.extend(self.subO('found'))
            res.extend(self.subO('street'))
            res.extend(self.subO('not found'))
            return res


    def move_sub(self,guid,tgt):
        if tgt.endswith('_b'):
            if self._subs.has_key('found_b'):
                self._subs['found_b'].discard(guid)

        if typ_cond.has_key(tgt):
            if self._subs.has_key('found'):
                self._subs['found'].discard(guid)
            if self._subs.has_key('street'):
                self._subs['street'].discard(guid)

        if self._subs.has_key(tgt):
            self._subs[tgt].add(guid)