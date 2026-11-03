"""Bounded public bulk readers; queues always come from the official OSR.

No application imports, subscriber queries, accounts, or test-address inputs.
Geographic names only discover streets; they never establish an outage queue.
"""
import argparse,base64,datetime,hashlib,json,re,time,urllib.parse,urllib.request,zipfile
from html.parser import HTMLParser
from pathlib import Path
from city_crawl import city_key,request_limit,scoped_state
from source_utils import clean,record

CONFIG={
 'ternopil':('UA-61','https://api-poweron.toe.com.ua/api/pw_address_queues?pagination=false'),
 'zhytomyr':('UA-18','https://www.ztoe.com.ua/unhooking-search.php'),
 'sumy':('UA-59','https://www.soe.com.ua/consumers/shutdowns'),
}
MAX_BYTES=24_000_000
class Bound(RuntimeError):pass
class HTTP:
 def __init__(self,limit,evidence=None):
  self.limit=limit;self.calls=0;self.deadline=time.monotonic()+480;self.trace=[];self.evidence=Path(evidence) if evidence else None
  if self.evidence:self.evidence.mkdir(parents=True,exist_ok=True)
  self.archive=self.evidence/('original-responses-'+str(time.time_ns())+'.zip') if self.evidence else None
 def read(self,url,fields=None,headers=None):
  if self.calls>=self.limit or time.monotonic()>=self.deadline:raise Bound('request_budget')
  from request_budget import throttle
  throttle(url);self.calls+=1;at=int(time.time()*1000)
  extra={'User-Agent':'Mozilla/5.0 (KolySvitlo official public address reader)','Accept':'application/json,text/html','Accept-Language':'uk'}
  if fields is not None:extra['Content-Type']='application/x-www-form-urlencoded'
  extra.update(headers or {});req=urllib.request.Request(url,data=urllib.parse.urlencode(fields).encode() if fields is not None else None,headers=extra)
  item={'url':url,'method':'POST' if fields is not None else 'GET','checkedAt':at}
  try:
   with urllib.request.urlopen(req,timeout=40) as r:
    raw=r.read(MAX_BYTES+1)
    if len(raw)>MAX_BYTES:raise ValueError('source_response_limit')
    item.update(status=r.status,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
    if self.archive:
     name='response-'+str(self.calls).zfill(4)+'-'+item['sha256'][:12]+'.bin'
     with zipfile.ZipFile(self.archive,'a',compression=zipfile.ZIP_DEFLATED) as archive:
      archive.writestr(name,raw);archive.writestr(name+'.json',json.dumps({**item,'publicFormFields':fields},ensure_ascii=False))
     item['artifact']={'archive':self.archive.name,'member':name,'sha256':item['sha256']}
    return raw
  except Exception as error:item.update(status=getattr(error,'code',None),error=type(error).__name__);raise
  finally:self.trace.append(item)
 def text(self,url,fields=None,headers=None):
  raw=self.read(url,fields,headers)
  charset='cp1251' if re.search(rb'charset\s*=\s*["\x27]?windows-1251',raw[:2500],re.I) else 'utf-8'
  return raw.decode(charset,'replace')
 def json(self,url,headers=None):return json.loads(self.read(url,headers=headers))

def geo(operator,target):
 values=json.loads(Path(__file__).with_name('capital-geography.json').read_text())['cities']
 found=[c for c in values if c['regionId']==CONFIG[operator][0] and city_key(c['settlement'])==city_key(target)]
 if len(found)!=1 or not found[0].get('community'):raise ValueError('verified_target_geography_required')
 return found[0]

def house(value):
 value=clean(value)
 return value if re.fullmatch(r'\d{1,4}(?:[ -]?[А-Яа-яІіЇїЄєҐґA-Za-z])?(?:/\d{1,4}[А-Яа-яІіЇїЄєҐґA-Za-z]?)?',value) else None

def house_key(value):
 return re.sub(r'(\d)[‐‑‒–—-](?=[а-яіїєґ]$)','\\1',str(value).casefold().replace(' ','').translate(str.maketrans('aceopx','асеорх')))

def qvalue(value):
 value=str(value or '').strip()
 if re.fullmatch(r'[1-6][12]',value):value=value[0]+'.'+value[1]
 return value if re.fullmatch(r'[1-9]\d?(?:\.\d{1,2})?',value) else None

def uncertain_scope(value):
 return bool(re.search(r'крім|окрім|винят|частков|під[’\']?їзд|ввід|ввод|секці|корпус',str(value or ''),re.I))

def house_parts(value):
 literals=[];ranges=[]
 if uncertain_scope(value):return [],[]
 for token in re.split('[,;\n]',str(value or '')):
  token=token.strip()
  if not token:continue
  h=house(token)
  if h:literals.append(h);continue
  m=re.fullmatch(r'(\d{1,4})\s*[-–—]\s*(\d{1,4})',token)
  if m and int(m[1])<=int(m[2]):ranges.append((int(m[1]),int(m[2])))
 return list(dict.fromkeys(literals)),ranges

def consolidate(operator,g,claims,at):
 """Every duplicate/unknown connection participates before any queue is chosen."""
 grouped={};ranges={};uncertain_streets={(c['streetId'],c['street']) for c in claims if c.get('uncertainScope')}
 for c in claims:
  key=(c['streetId'],c['street'])
  for lo,hi in c.get('ranges',[]):ranges.setdefault(key,[]).append((lo,hi,c['queue']))
  for h in c['houses']:grouped.setdefault((*key,house_key(h)),[]).append((h,c))
 rows=[];observed=[]
 for (sid,street,_),values in grouped.items():
  h=values[0][0];qs=[c['queue'] for _,c in values];q=qs[0] if qs and all(qs) and len(set(qs))==1 else None
  if (sid,street) in uncertain_streets:q=None
  number=int(re.match(r'\d+',h)[0])
  if any(lo<=number<=hi and other!=q for lo,hi,other in ranges.get((sid,street),[])):q=None
  selected=values[0][1];observed_at=min(c.get('checkedAt',at) for _,c in values);observation={'regionId':g['regionId'],'settlement':g['settlement'],'community':g['community'],'street':street,'house':h,'checkedAt':observed_at,'expiresAt':observed_at+86400000}
  if sid:observation['providerStreetId']=str(sid)
  observed.append(observation)
  if not q:continue
  item=record(operator,g['regionId'],g['settlement'],g['community'],street,h,q,selected['sourceUrl'],observed_at)
  if not item:continue
  if selected.get('cityId') is not None:item['providerCityId']=str(selected['cityId'])
  if sid:item['providerStreetId']=str(sid)
  if sid and selected.get('cityId') is not None:item['officialCityId']=str(selected['cityId'])+':'+str(sid)
  rows.append(item)
 return rows,observed

def hydra_rows(value):
 if isinstance(value,list):return value
 if not isinstance(value,dict):raise ValueError('invalid_public_dictionary')
 rows=value.get('hydra:member',value.get('member'))
 if not isinstance(rows,list) or value.get('hydra:totalItems',len(rows))>len(rows):raise ValueError('incomplete_public_dictionary')
 return rows

def parse_ternopil(value,g,url,at):
 rows=hydra_rows(value);matched=[r for r in rows if isinstance(r,dict) and city_key((r.get('city') or {}).get('name'))==city_key(g['settlement'])]
 ids={str(r['city'].get('id')) for r in matched}
 if len(ids)!=1 or 'None' in ids:raise ValueError('target_city_not_unique')
 stem=re.sub(r'\s+(?:територіальна|міська|селищна|сільська|громада)\b','',g['community'],flags=re.I).strip()
 claims=[];street_ids=set()
 for row in matched:
  city=row['city'];street=row.get('street') or {};otg=row.get('otg') or {}
  if not street.get('id') or not isinstance(street.get('name'),str) or city_key(otg.get('name'))!=city_key(stem):raise ValueError('target_source_geography_mismatch')
  literals,ranges=house_parts(row.get('buildingNames'));sid=str(street['id']);street_ids.add(str(city['id'])+':'+sid)
  claims.append({'cityId':str(city['id']),'streetId':sid,'street':street['name'],'houses':literals,'ranges':ranges,'uncertainScope':uncertain_scope(row.get('buildingNames')),'queue':qvalue(row.get('chergGpv')),'sourceUrl':url})
 normalized,observed=consolidate('ternopil',g,claims,at)
 return normalized,observed,sorted(street_ids),{'sourceRows':len(rows),'targetRows':len(matched),'targetCityIds':sorted(ids),'dictionaryComplete':True,'sourceTraversal':'complete-public-grouped-table'}

class Form(HTMLParser):
 def __init__(self):super().__init__(convert_charrefs=True);self.select=None;self.option=None;self.options={};self.row=None;self.cell=None;self.rows=[];self.form=None;self.hidden={}
 def handle_starttag(self,tag,attrs):
  attrs=dict(attrs)
  if tag=='form':self.form=attrs.get('id','')
  if tag=='input' and self.form=='mainform2' and attrs.get('name') and attrs.get('type') in ('hidden','submit'):self.hidden[attrs['name']]=attrs.get('value','')
  if tag=='select':self.select=attrs.get('name');self.options.setdefault(self.select,[])
  if tag=='option' and self.select:self.option={'id':attrs.get('value',''),'name':''}
  if tag=='tr':self.row=[]
  if tag in ('td','th') and self.row is not None:self.cell=''
  if tag=='br' and self.cell is not None:self.cell+=';'
 def handle_data(self,text):
  if self.option is not None:self.option['name']+=text
  if self.cell is not None:self.cell+=text
 def handle_endtag(self,tag):
  if tag=='form':self.form=None
  if tag=='option' and self.option is not None:
   if self.option['id'] not in ('','0'):self.options[self.select].append({**self.option,'name':clean(self.option['name'])})
   self.option=None
  if tag=='select':self.select=None
  if tag in ('td','th') and self.cell is not None:
   if self.row is not None:self.row.append(clean(self.cell))
   self.cell=None
  if tag=='tr' and self.row is not None:self.rows.append(self.row);self.row=None

def form(body):p=Form();p.feed(body);return p

def zhytomyr_claims(body,g,url,at):
 parsed=form(body)
 if not any(len(r)==7 and r[1]=='Населений пункт' and r[4]=='Черга' and r[5]=='Підчерга' for r in parsed.rows):raise ValueError('official_gpv_table_header_missing')
 claims=[]
 for cells in parsed.rows:
  if len(cells)!=7 or city_key(cells[1])!=city_key(g['settlement']):continue
  literals,ranges=house_parts(cells[3]);q=cells[4]+'.'+cells[5] if re.fullmatch('[1-6]',cells[4]) and re.fullmatch('[12]',cells[5]) else None
  claims.append({'streetId':None,'street':cells[2],'houses':literals,'ranges':ranges,'uncertainScope':uncertain_scope(cells[3]),'queue':q,'sourceUrl':url,'checkedAt':at})
 return claims

def parse_zhytomyr(body,g,url,at):
 claims=zhytomyr_claims(body,g,url,at)
 return consolidate('zhytomyr',g,claims,at),len(claims)

def zhytomyr(http,g,state):
 url=CONFIG['zhytomyr'][1];initial=form(http.text(url));departments=initial.options.get('rem_id',[])
 if not departments:raise ValueError('official_department_dictionary_missing')
 signature=hashlib.sha256(json.dumps(departments,sort_keys=True).encode()).hexdigest();directory=state.setdefault('targetDirectory',{})
 if directory.get('signature')!=signature or directory.get('checkedAt',0)<int(time.time()*1000)-86400000:
  directory.clear();directory.update(signature=signature,index=0,targets=[],checkedAt=int(time.time()*1000),complete=False)
 pages={};errors=[]
 # First discover every branch listing this same city. Reading one REM must
 # not hide another connection at the same building in another REM.
 try:
  while not directory['complete'] and directory['index']<len(departments):
   department=departments[directory['index']];page=http.text(url,{'rem_id':department['id']});at=int(time.time()*1000);parsed=form(page);pages[department['id']]=(page,at)
   if any(city_key(c['name'])==city_key(g['settlement']) for c in parsed.options.get('naspunkt_id',[])):
    if department['id'] not in directory['targets']:directory['targets'].append(department['id'])
   directory['index']+=1
  if directory['index']>=len(departments):directory['complete']=True
 except Exception as error:errors.append({'stage':'target_branch_dictionary','error':type(error).__name__})
 if not directory['complete']:return [],[],[],{'departmentIdsRead':[],'departmentsKnown':len(departments),'dictionaryComplete':False,'dictionaryBranchesScanned':directory['index']},errors
 if not directory['targets']:raise ValueError('target_city_not_in_official_departments')
 claims=[];done=[]
 for department_id in directory['targets']:
  try:
   if department_id in pages:page,at=pages[department_id]
   else:page=http.text(url,{'rem_id':department_id});at=int(time.time()*1000)
   parsed=form(page)
   # Submit only the all-button/hidden fields actually offered anonymously.
   if 'all' in parsed.hidden:page=http.text(url,parsed.hidden);at=int(time.time()*1000)
   claims.extend(zhytomyr_claims(page,g,url,at));done.append(department_id)
  except Exception as error:errors.append({'stage':'target_branch_read','departmentId':department_id,'error':type(error).__name__});break
 meta={'departmentIdsRead':done,'targetDepartmentIds':directory['targets'],'departmentsKnown':len(departments),'dictionaryComplete':len(done)==len(directory['targets']),'sourceTraversal':'all-official-city-branches-before-house-consensus'}
 if not meta['dictionaryComplete']:return [],[],[],meta,errors
 rows,observed=consolidate('zhytomyr',g,claims,int(time.time()*1000))
 return rows,observed,[],meta,errors

def sumy_key(prefix,now,offset=0):
 d=datetime.datetime.fromtimestamp(now/1000,datetime.timezone.utc);period=d.minute//5+offset
 stamp=f'{d.year}-{d.month-1}-{d.day}-{d.hour}-{period}'
 return (prefix+stamp).ljust(32,'x')[:32].encode()

def decode_sumy(value,prefix,now):
 if not isinstance(value,dict):raise ValueError('sumy_response_not_object')
 if 'payload' not in value:return value.get('data',value)
 if not isinstance(value['payload'],str) or len(value['payload'])>MAX_BYTES*2:raise ValueError('sumy_payload_limit')
 raw=base64.b64decode(value['payload'],validate=True)
 if len(raw)<29:raise ValueError('sumy_payload_truncated')
 from cryptography.hazmat.primitives.ciphers.aead import AESGCM
 for offset in (0,-1):
  try:
   decoded=json.loads(AESGCM(sumy_key(prefix,now,offset)).decrypt(raw[:12],raw[12:],None));return decoded.get('data',decoded)
  except Exception:pass
 raise ValueError('sumy_public_client_codec_changed')

def sumy_protocol(http,state):
 base='https://www.soe.com.ua';page=http.text(CONFIG['sumy'][1]);urls=list(dict.fromkeys(urllib.parse.urljoin(base,u) for u in re.findall(r'<script[^>]*src="([^"]+)',page)))
 saved=state.get('protocol',{});ordered=[u for u in [saved.get('codecUrl'),saved.get('queueLabelsUrl')] if u in urls]+urls
 prefix=None;gpv=False;proof=[]
 for url in dict.fromkeys(ordered):
  if urllib.parse.urlsplit(url).hostname!='www.soe.com.ua':continue
  text=http.text(url)
  if 'AES-GCM' in text and 'soe-website' in text and 'X-Source' in text and '.slice(0,32)' in text:
   match=re.search(r'return`([^`$]+)\$\{\w+\}`\.padEnd\(32,"x"\)\.slice\(0,32\)',text)
   if match and 16<=len(match[1])<=100:prefix=match[1];state.setdefault('protocol',{})['codecUrl']=url;proof.append({'url':url,'sha256':hashlib.sha256(text.encode()).hexdigest(),'kind':'public-client-codec'})
  if re.search(r'\{(?:index|type):3,label:"ГПВ"\}',text):gpv=True;state.setdefault('protocol',{})['queueLabelsUrl']=url;proof.append({'url':url,'sha256':hashlib.sha256(text.encode()).hexdigest(),'kind':'GPV-array-index3'})
  if prefix and gpv:return prefix,proof
 raise ValueError('current_official_sumy_codec_or_queue_labels_unverified')

def sumy_list(value):
 if value=='':return []
 if not isinstance(value,dict) or value.get('result')!=0 or not isinstance(value.get('list'),list):raise ValueError('sumy_public_list_codec_changed')
 return value['list']

def parse_sumy_queue(value,g,city_id,street,url,at):
 claims=[]
 for row in sumy_list(value):
  if not isinstance(row,list) or len(row)!=4 or not isinstance(row[3],list) or len(row[3])!=7:raise ValueError('sumy_house_queue_shape_changed')
  if city_key(re.sub(r'\s*\([^()]*\)\s*$','',str(row[0])))!=city_key(g['settlement']) or clean(row[1])!=clean(street['name']):raise ValueError('sumy_house_crosses_geography')
  h=house(row[2])
  if not h:continue
  claims.append({'cityId':str(city_id),'streetId':str(street['id']),'street':street['name'],'houses':[h],'queue':qvalue(row[3][3]),'sourceUrl':url})
 return consolidate('sumy',g,claims,at)

def geographic_queries(value):
 names={clean(e.get('tags',{}).get('name')) for e in value.get('elements',[]) if e.get('tags',{}).get('name')}
 types=r'вулиця|вул\.?|улица|ул\.?|проспект|просп\.?|провулок|пров\.?|бульвар|бул\.?|площа|пл\.?|узвіз|набережна|проїзд|шосе|дорога|тупик|алея'
 terms=set()
 for name in names:
  stripped=re.sub(r'^(?:'+types+r')\s+|\s+(?:'+types+r')$','',name,flags=re.I).strip()
  if len(stripped)>=3:terms.add(stripped)
  terms.update(w for w in re.findall(r'[А-Яа-яІіЇїЄєҐґA-Za-z’\'-]{3,}',stripped) if not re.fullmatch(types,w,re.I))
 if not terms:raise ValueError('geographic_street_inventory_unavailable')
 return names,terms

def source_street_queries(http,g,state):
 if state.get('streetQueries') is not None:return
 # External geographic street names only discover OSR IDs. This is not a list
 # of test addresses and does not attach a guessed queue to any geographic row.
 query='[out:json][timeout:35];area('+str(3600000000+g['osmRelation'])+')->.a;way["highway"]["name"](area.a);out tags;'
 failures=[];raw=None;source=None
 for server,post in [('https://overpass-api.de/api/interpreter',True),('https://overpass-api.de/api/interpreter',False),('https://overpass.kumi.systems/api/interpreter',True)]:
  try:
   url=server if post else server+'?'+urllib.parse.urlencode({'data':query});raw=http.read(url,{'data':query} if post else None);source=url;break
  except Bound:raise
  except Exception as error:failures.append(type(error).__name__)
 if raw is None:raise ValueError('geographic_street_inventory_unavailable:'+','.join(failures))
 value=json.loads(raw)
 names,terms=geographic_queries(value)
 state['streetQueries']=sorted(terms,key=lambda t:hashlib.sha256(t.encode()).hexdigest());state['streetQueryIndex']=0
 state['geographicInventory']={'sourceUrl':source,'sha256':hashlib.sha256(raw).hexdigest(),'streets':len(names),'terms':len(terms),'checkedAt':int(time.time()*1000),'attribution':'© OpenStreetMap contributors, ODbL'}

def sumy(http,g,state):
 prefix,proof=sumy_protocol(http,state);base='https://www.soe.com.ua/next-api/';headers={'X-Source':'soe-website','Referer':CONFIG['sumy'][1],'Origin':'https://www.soe.com.ua'}
 def call(path,params):
  url=base+path+'?'+urllib.parse.urlencode(params);value=decode_sumy(http.json(url,headers),prefix,int(time.time()*1000));return value,url
 cities,_=call('shutdowns/cities',{'search':g['settlement']});found=[r for r in sumy_list(cities) if isinstance(r,list) and len(r)==2 and city_key(r[1])==city_key(g['settlement'])]
 if len(found)!=1:raise ValueError('sumy_target_city_not_unique')
 city_id=found[0][0];source_street_queries(http,g,state);inventory=state.setdefault('officialStreets',{});errors=[];rows=[];observed=[];completed=[]
 # Reserve roughly half the remaining request budget for house/GV reads. A
 # fixed first12 search terms would take weeks to discover a large city.
 for _ in range(max(1,min(200,(http.limit-http.calls-4)//2))):
  index=state.get('streetQueryIndex',0)
  if index>=len(state['streetQueries']):break
  try:
   values,_=call('shutdowns/streets',{'cityId':city_id,'search':state['streetQueries'][index]})
   for r in sumy_list(values):
    if not isinstance(r,list) or len(r)!=2:raise ValueError('sumy_street_dictionary_shape')
    inventory[str(r[0])]={'id':str(r[0]),'name':r[1]}
   state['streetQueryIndex']=index+1
  except Exception as error:errors.append({'stage':'street_dictionary','error':type(error).__name__});break
 ordered=sorted(inventory.values(),key=lambda r:r['id']);by_id={r['id']:i for i,r in enumerate(ordered)};position=by_id.get(state.get('nextStreetId'),state.get('streetIndex',0)%max(1,len(ordered)))
 while position<len(ordered):
  street=ordered[position]
  try:
   value,url=call('shutdowns/queues-by-street',{'streetId':street['id']});at=int(time.time()*1000);r,o=parse_sumy_queue(value,g,city_id,street,url,at);rows.extend(r);observed.extend(o);completed.append(str(city_id)+':'+street['id']);position+=1;state['streetIndex']=position;state['nextStreetId']=ordered[position]['id'] if position<len(ordered) else None
  except Exception as error:errors.append({'stage':'street_queue','streetId':street['id'],'error':type(error).__name__});break
 if position>=len(ordered):state['streetIndex']=0;state['nextStreetId']=None;state['cycles']=state.get('cycles',0)+1
 return rows,observed,completed,{'dictionaryComplete':False,'officialStreetCount':len(inventory),'geographicDiscoveryQueries':state.get('streetQueryIndex',0),'geographicInventory':state.get('geographicInventory'),'publicProtocolProof':proof,'sourceTraversal':'OSM-discovery-to-official-city/street-dictionary-and-house-GPV-column3'},errors

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--operator',choices=CONFIG,required=True);p.add_argument('--target-city',required=True);p.add_argument('--output',required=True);p.add_argument('--state');p.add_argument('--full-city',action='store_true');p.add_argument('--request-limit',type=request_limit,default=120);p.add_argument('--evidence-directory');p.add_argument('--budget',type=int);p.add_argument('--street-limit',type=int);p.add_argument('--city-limit',type=int);args=p.parse_args()
 g=geo(args.operator,args.target_city);output=Path(args.output);statefile=Path(args.state) if args.state else output.with_suffix('.state.json');saved=json.loads(statefile.read_text()) if statefile.exists() else {};state=scoped_state(saved,args.target_city,True);http=HTTP(args.request_limit,args.evidence_directory);rows=[];observed=[];completed=[];meta={};errors=[]
 try:
  if args.operator=='ternopil':
   url=CONFIG[args.operator][1];value=http.json(url);at=int(time.time()*1000);rows,observed,completed,meta=parse_ternopil(value,g,url,at)
  else:rows,observed,completed,meta,errors=globals()[args.operator](http,g,state)
 except Exception as error:errors.append({'stage':'collection','error':type(error).__name__,'httpStatus':getattr(error,'code',None),'reason':str(error)[:180]})
 at=int(time.time()*1000);output.parent.mkdir(parents=True,exist_ok=True);statefile.parent.mkdir(parents=True,exist_ok=True);tmp=statefile.with_suffix('.tmp');tmp.write_text(json.dumps(saved,ensure_ascii=False,indent=2)+'\n');tmp.replace(statefile)
 report={'operatorId':args.operator,'checkedAt':at,'records':len(rows),'observedHouses':len(observed),'requestCount':http.calls,'requests':http.trace,'errors':errors,'cityCrawl':{'targetCity':g['settlement'],'mode':'official-public-bulk-table','status':'complete' if meta.get('dictionaryComplete') else 'partial',**meta},'method':'source-derived official facts, not independent Android address coverage'}
 Path(str(output)+'.report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 if rows or observed:
  bundle={'schemaVersion':1,'operatorId':args.operator,'generatedAt':at,'expiresAt':max([r['expiresAt'] for r in rows]+[o['expiresAt'] for o in observed]),'records':rows,'observedHouses':observed,'completedStreetIds':completed};output.write_text(json.dumps(bundle,ensure_ascii=False,separators=(',',':'))+'\n')
 print(json.dumps({'operatorId':args.operator,'records':len(rows),'observedHouses':len(observed),'requests':http.calls,'errors':errors[:3]},ensure_ascii=False))
 if not rows and not observed:raise SystemExit(2)
if __name__=='__main__':main()
