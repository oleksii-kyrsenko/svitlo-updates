"""Bounded standalone official address collectors. No private application imports.
Only explicit house/queue assignments survive. Subscriber identifiers stay in memory.
"""
import argparse,datetime,hashlib,json,random,re,time,urllib.parse
from html.parser import HTMLParser
from pathlib import Path
from source_utils import Fetch,clean,locality,record
REGIONS={'mykolaiv':('UA-48','Миколаївська область'),'chernivtsi':('UA-73','Чернівецька область'),'zhytomyr':('UA-18','Житомирська область'),'cherkasy':('UA-71','Черкаська область'),'sumy':('UA-59','Сумська область')}
URLS={'mykolaiv':'https://off.energy.mk.ua/','chernivtsi':'https://oblenergo.cv.ua/shutdowns/','zhytomyr':'https://www.ztoe.com.ua/unhooking-search.php','cherkasy':'https://www.cherkasyoblenergo.com/off','sumy':'https://www.soe.com.ua/consumers/shutdowns'}
class Form(HTMLParser):
 def __init__(self):super().__init__(convert_charrefs=True);self.select=None;self.option=None;self.options={};self.row=None;self.cell=None;self.rows=[];self.hidden={};self.activeform=None
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if tag=='form':self.activeform=a.get('id','')
  if tag=='input' and self.activeform=='mainform2' and a.get('name') and a.get('type') in ('hidden','submit'):self.hidden[a['name']]=a.get('value','')
  if tag=='select':self.select=a.get('name');self.options.setdefault(self.select,[])
  if tag=='option' and self.select:self.option={'id':a.get('value',''),'name':''}
  if tag=='tr':self.row=[]
  if tag in ('td','th') and self.row is not None:self.cell=''
 def handle_data(self,data):
  if self.option is not None:self.option['name']+=data
  if self.cell is not None:self.cell+=data+' '
 def handle_endtag(self,tag):
  if tag=='form':self.activeform=None
  if tag=='option' and self.option is not None:
   if self.option['id'] not in ('','0'):self.options[self.select].append({**self.option,'name':clean(self.option['name'])})
   self.option=None
  if tag=='select':self.select=None
  if tag in ('td','th') and self.cell is not None:
   if self.row is not None:self.row.append(clean(self.cell))
   self.cell=None
  if tag=='tr' and self.row is not None:self.rows.append(self.row);self.row=None

def form(body):p=Form();p.feed(body);return p

def houses(value):
 values=[clean(x) for x in re.split('[,;\n]',value)]
 # Unknown qualifiers and ranges cannot be silently expanded or partially kept.
 if not values or any(not re.fullmatch(r'\d{1,4}(?:[- ]?[А-Яа-яІіЇїЄєҐґA-Za-z])?(?:/\d{1,4}[А-Яа-яІіЇїЄєҐґA-Za-z]?)?',x) for x in values):return []
 return values

def consensus(rows):
 grouped={}
 for r in rows:grouped.setdefault((r['settlement'],r['community'],r['street'],r.get('officialCityId'),r['houses'][0]),[]).append(r)
 return [group[0] for group in grouped.values() if len({r['queue'] for r in group})==1]

def parse_chernivtsi(body,branch):
 title=re.search(r'<title>(.*?)</title>',body,re.I|re.S);city=clean(title[1]).split('/')[0].strip() if title else ''
 if not title or not re.search('Пошук групи',clean(title[1]),re.I):raise ValueError('unknown_directory_title')
 rows=[]
 for match in re.finditer(r'<div>\s*(?:<s>([^<]+)</s>)?\s*<p>([^<]+)</p>\s*<b>([^<]+)</b>\s*<u>(\d+)</u>\s*</div>',body,re.I):
  settlement=clean(match[1] or city);street=clean(match[2]);house=re.sub(r'^буд\.\s*','',clean(match[3]),flags=re.I)
  if house and street and settlement and not re.search(r'дільниц|район|відключ|пошук',settlement,re.I):rows.append({'settlement':settlement,'street':street,'house':house,'queue':match[4],'branch':str(branch)})
 if not rows:raise ValueError('directory_no_addresses')
 return rows

class Collector:
 def __init__(self,operator,budget=100,state=None,geography=None,target_city=None,full_city=False):
  self.op=operator;self.f=Fetch(budget);self.state=state or {};self.rows=[];self.errors=[];self.checks=[];self.contexts=[];self.completed=[];self.deadline=time.monotonic()+180;self.verifyForms={}
  self.target_city=target_city;self.full_city=full_city;self.traversal={'targetCity':target_city,'cycleComplete':False,'mode':'resumable-city-dictionary' if full_city else 'legacy-bounded-discovery'}
  if full_city:
   if not target_city:raise ValueError('full_city_requires_target_city')
   self.deadline=time.monotonic()+900;self.f.deadline=self.deadline
  if geography is None:
   from geography import GeographyResolver
   geography=GeographyResolver(cache_path='coverage/geography-cache.json')
  self.geo=geography
 def context(self,name):
  query={'settlement':name,'regionId':REGIONS[self.op][0]};result=self.geo.resolve(query);self.contexts.append(result)
  return result.get('community') if result.get('status')=='resolved' else None
 def add(self,settlement,community,street,house,queue,source,identity=None):
  r=record(self.op,REGIONS[self.op][0],settlement,community,street,house,queue,source,int(time.time()*1000),identity)
  if r:self.rows.append(r)
  return r
 def error(self,stage,error):self.errors.append({'stage':stage,'error':type(error).__name__,'httpStatus':getattr(error,'code',None)})
 def check(self,settlement,street,house,queue,status='confirmed'):
  self.checks.append({'settlement':settlement,'street':street,'house':house,'queue':queue,'status':status})
 def city_entries(self):
  """Discover the requested city from official dictionaries, not an address fixture."""
  entries=[]
  if self.op=='mykolaiv':
   base=URLS[self.op]+'api/';branches=self.f.json(base+'addr/filii')
   for branch in branches:
    for city in self.f.json(base+f"addr/filii/{branch['idfilial']}/ns"):
     name=next((city[k] for k in ('naznaspunkt','naspunkt','name','fullname') if city.get(k)),None)
     if locality(name)==locality(self.target_city):entries.append({'id':str(city['idnaspunkt']),'name':name})
  elif self.op=='zhytomyr':
   url=URLS[self.op];deps=form(self.f.text(url)).options.get('rem_id',[])
   if not deps:raise ValueError('department_form_missing')
   for dep in deps:
    for city in form(self.f.text(url,{'rem_id':dep['id']})).options.get('naspunkt_id',[]):
     if locality(city['name'])==locality(self.target_city):entries.append({'id':city['id'],'departmentId':dep['id'],'name':city['name']})
  elif self.op=='cherkasy':
   api='https://cabinet.cherkasyoblenergo.com/api_new/disconn.php'
   def query(**params):
    value=self.f.json(api+'?'+urllib.parse.urlencode(params));return list(value.values()) if isinstance(value,dict) else value
   for branch in query(op='department_list'):
    for city in query(op='city_list',dept_id=branch['ID']):
     if locality(city['NAME'])==locality(self.target_city):entries.append({'id':str(city['ID']),'name':city['NAME'],'community':city.get('community')})
  # Duplicate city IDs returned under different branches represent one official
  # city dictionary; do not waste each cycle rereading it.
  return list({(entry.get('departmentId'),entry['id']):entry for entry in entries}.values())
 def collect_city(self):
  if self.op=='chernivtsi':
   self.chernivtsi();return
  if self.op=='sumy':
   self.sumy();return
  entries=self.city_entries()
  if not entries:raise ValueError('target_city_not_in_official_dictionary')
  signature=hashlib.sha256(json.dumps(entries,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
  cursor=self.state.get('targetCursor',{})
  if cursor.get('target')!=locality(self.target_city) or cursor.get('directorySignature')!=signature:cursor={'target':locality(self.target_city),'directorySignature':signature,'entryIndex':0,'streetIndex':0,'houseIndex':0}
  self.state['targetCursor']=cursor
  while cursor['entryIndex']<len(entries):
   entry=entries[cursor['entryIndex']];community=entry.get('community') or self.context(entry['name'])
   if not community:raise ValueError('verified_target_community_missing')
   self.collect_entry(entry,community,cursor)
   if cursor.get('entryComplete'):
    cursor.update(entryIndex=cursor['entryIndex']+1,streetIndex=0,houseIndex=0,entryComplete=False)
   else:return
  self.traversal.update(cycleComplete=True,officialCityCount=len(entries));cursor.update(entryIndex=0,streetIndex=0,houseIndex=0)
 def collect_entry(self,entry,community,cursor):
  """Resume on the first unread house/street; never first-N random streets."""
  if self.op=='mykolaiv':
   base=URLS[self.op]+'api/'
   streets=self.f.json(base+f"addr/ns/{entry['id']}/street")
  elif self.op=='zhytomyr':
   fields={'rem_id':entry['departmentId'],'naspunkt_id':entry['id']}
   streets=form(self.f.text(URLS[self.op],fields)).options.get('vulica_id',[])
  else:
   api='https://cabinet.cherkasyoblenergo.com/api_new/disconn.php'
   def q(**params):
    value=self.f.json(api+'?'+urllib.parse.urlencode(params));return value if params.get('op')=='disconn_by_ls' else list(value.values()) if isinstance(value,dict) else value
   streets=q(op='street_list',city_id=entry['id'],search_name='')
  if not isinstance(streets,list) or not streets:raise ValueError('target_street_dictionary_missing')
  for si in range(cursor['streetIndex'],len(streets)):
   if self.f.calls>=self.f.budget-5 or time.monotonic()>self.deadline:return
   street=streets[si]
   if self.op=='zhytomyr':
    request_fields={**fields,'vulica_id':street['id']};parsed=form(self.f.text(URLS[self.op],request_fields))
    if parsed.hidden:request_fields=parsed.hidden;parsed=form(self.f.text(URLS[self.op],request_fields))
    for row in parsed.rows:
     if len(row)!=7 or locality(row[1])!=locality(entry['name']) or not re.fullmatch('[1-6]',row[4]) or not re.fullmatch('[12]',row[5]):continue
     for house in houses(row[3]):
      r=self.add(entry['name'],community,row[2],house,row[4]+'.'+row[5],URLS[self.op])
      if r:self.check(entry['name'],row[2],house,r['queue'],'confirmed_official_form')
    cursor.update(streetIndex=si+1,houseIndex=0);continue
   if self.op=='mykolaiv':house_rows=self.f.json(base+f"addr/street/{street['idstreet']}/dom")
   else:house_rows=q(op='house_list',street_id=street['ID'],search_name='')
   if not isinstance(house_rows,list):raise ValueError('target_house_dictionary_invalid')
   for hi in range(cursor['houseIndex'],len(house_rows)):
    if self.f.calls>=self.f.budget-5 or time.monotonic()>self.deadline:return
    h=house_rows[hi]
    if self.op=='mykolaiv':
     sn=next((street[k] for k in ('nazstreet','street','name','fullname') if street.get(k)),None);hn=str(next((h[k] for k in ('nazdom','dom','name','fullname') if h.get(k)),''))
     qr=self.f.json(base+f"addr/dom/{h['iddom']}/outage-queue");values=[str(v['outage'].get('name','')) for v in qr if v.get('outage',{}).get('type_id')==3]
     queue=values[0] if values and len(set(values))==1 and all(re.fullmatch(r'\d{1,2}(?:\.\d{1,2})?',v) for v in values) else None
    else:
     sn=street['NAME'];hn=str(h['HOUSE']);accounts=q(op='ls_list_by_addr',street_id=street['ID'],house=hn);values=[]
     if len(accounts)>64:self.check(entry['name'],sn,hn,None,'too_many_connections');cursor['houseIndex']=hi+1;continue
     # No partially read connection list can confirm a whole house.
     if self.f.calls+len(accounts)>self.f.budget-2:return
     for account in accounts:
      date=datetime.datetime.now(datetime.timezone.utc).strftime('%d.%m.%Y')
      data=q(op='disconn_by_ls',disconn_selector='2',n_date=date,k_date=date,abon_ls=account['LS'])
      sections=data.get('DISCONN_QUEUQ',{}) if isinstance(data,dict) else {}
      sections=list(sections.values()) if isinstance(sections,dict) else sections;found=[]
      for section in sections:
       for part in re.split(r'(?=(?:СГАВ|ГАВ|ГПВ))',clean(section.get('QUEUE_INFO',''))):
        if 'ГПВ' in part or 'погодин' in part.lower():
         found.extend(a+'.'+b for a,b in re.findall(r'([1-6])\s*черг[аиу]\s*[,;:–—-]?\s*([12])\s*підчерг[аиу]',part,re.I));found.extend(a+'.'+b for a,b in re.findall(r'(?<![\d.])([1-6])\s*[.,]\s*([12])(?![\d.])',part))
      values.append(found[0] if found and len(set(found))==1 else None)
     queue=values[0] if values and all(values) and len(set(values))==1 else None
    if queue:self.add(entry['name'],community,sn,hn,queue,URLS[self.op]);self.check(entry['name'],sn,hn,queue)
    else:self.check(entry['name'],sn,hn,None,'ambiguous_or_no_gpv')
    cursor['houseIndex']=hi+1
   cursor.update(streetIndex=si+1,houseIndex=0)
  cursor['entryComplete']=True
 def mykolaiv(self):
  base=URLS[self.op]+'api/';branches=self.f.json(base+'addr/filii');start=self.state.get('branchIndex',0)%len(branches)
  for bi in range(start,min(len(branches),start+3)):
   cities=self.f.json(base+f"addr/filii/{branches[bi]['idfilial']}/ns")
   for city in cities[self.state.get('cityIndex',0):][:6]:
    if time.monotonic()>self.deadline:return
    name=city.get('naznaspunkt') or city.get('naspunkt') or city.get('name') or city.get('fullname');community=self.context(name)
    if not community:continue
    streets=self.f.json(base+f"addr/ns/{city['idnaspunkt']}/street");pool=[]
    for street in streets[self.state.get('streetIndex',0):][:8]:
     try:
      for house in self.f.json(base+f"addr/street/{street['idstreet']}/dom"):pool.append((street,house))
     except Exception as e:self.error('house_dictionary',e)
    # Address sample is selected before queue queries, independently of queue values.
    random.Random(str(city['idnaspunkt'])+'|coverage').shuffle(pool)
    for street,house in pool[:max(20,min(60,self.f.budget-self.f.calls-2))]:
     if time.monotonic()>self.deadline:return
     sn=street.get('nazstreet') or street.get('street') or street.get('name') or street.get('fullname');hn=house.get('nazdom') or house.get('dom') or house.get('name') or house.get('fullname')
     try:
      queue_rows=self.f.json(base+f"addr/dom/{house['iddom']}/outage-queue");queues=[str(q['outage'].get('name','')) for q in queue_rows if q.get('outage',{}).get('type_id')==3]
      queue=queues[0] if queues and len(set(queues))==1 and all(re.fullmatch(r'\d{1,2}(?:\.\d{1,2})?',q) for q in queues) else None
      if queue:self.add(name,community,sn,str(hn),queue,URLS[self.op]);self.check(name,sn,str(hn),queue)
      elif len(self.checks)<20:self.check(name,sn,str(hn),None,'ambiguous_or_no_gpv')
     except Exception as e:self.error('queue_lookup',e)
     if self.f.calls>=self.f.budget-1:break
    self.state.update(branchIndex=bi,cityIndex=cities.index(city)+1,streetIndex=0)
    return
   self.state.update(branchIndex=(bi+1)%len(branches),cityIndex=0,streetIndex=0)
 def chernivtsi(self):
  branch=self.state.get('branch',1);url=f'https://oblenergo.cv.ua/shutdowns-search/{branch}/';body=self.f.text(url);source_rows=parse_chernivtsi(body,branch);by_city={}
  for r in source_rows:by_city.setdefault(r['settlement'],[]).append(r)
  selected=[(name,rows) for name,rows in by_city.items() if not self.full_city or locality(name)==locality(self.target_city)]
  for name,rows in selected if self.full_city else selected[:6]:
   community=self.context(name)
   if not community:continue
   claims={}
   for item in rows:claims.setdefault((item['street'],item['house']),set()).add(item['queue'])
   for item in rows:
    if len(claims[(item['street'],item['house'])])!=1:continue
    identity=hashlib.sha256((str(branch)+'|'+name+'|'+item['street']).encode()).hexdigest()[:24]
    added=self.add(name,community,item['street'],item['house'],item['queue'],url,identity+'|'+item['house'])
    if added:added['officialCityId']='chernivtsi:'+str(branch)+':'+identity
  self.rows=consensus(self.rows)
  sample=random.Random(str(branch)+'|coverage').sample(self.rows,min(20,len(self.rows)))
  if sample:
   reread=parse_chernivtsi(self.f.text(url),branch);lookup={}
   for r in reread:lookup.setdefault((r['settlement'],r['street'],r['house']),set()).add(r['queue'])
   for r in sample:
    values=lookup.get((r['settlement'],r['street'],r['houses'][0]),set());self.check(r['settlement'],r['street'],r['houses'][0],r['queue'],'confirmed_source_reread' if values=={r['queue']} else 'conflict')
  self.state['branch']=branch%12+1
  if self.full_city:self.traversal.update(sourceBranch=branch,targetCityInBranch=bool(selected),branchComplete=True,cycleComplete=False,remainingBranchesMustBeChecked=True)
 def zhytomyr(self):
  url=URLS[self.op];initial=form(self.f.text(url));deps=initial.options.get('rem_id',[])
  if not deps:raise ValueError('department_form_missing')
  di=self.state.get('departmentIndex',0)%len(deps);dep=deps[di];cp=form(self.f.text(url,{'rem_id':dep['id']}));cities=cp.options.get('naspunkt_id',[])
  for ci in range(self.state.get('cityIndex',0),min(len(cities),self.state.get('cityIndex',0)+5)):
   city=cities[ci];community=self.context(city['name'])
   if not community:continue
   fields={'rem_id':dep['id'],'naspunkt_id':city['id']};page=form(self.f.text(url,fields));streets=page.options.get('vulica_id',[])
   for si in range(self.state.get('streetIndex',0),min(len(streets),self.state.get('streetIndex',0)+8)):
    street=streets[si];request_fields={**fields,'vulica_id':street['id']};parsed=form(self.f.text(url,request_fields))
    if parsed.hidden:request_fields=parsed.hidden;parsed=form(self.f.text(url,request_fields))
    found=[]
    for row in parsed.rows:
     if len(row)!=7 or locality(row[1])!=locality(city['name']) or not re.fullmatch('[1-6]',row[4]) or not re.fullmatch('[12]',row[5]):continue
     for house in houses(row[3]):
      r=self.add(city['name'],community,row[2],house,row[4]+'.'+row[5],url)
      if r:found.append(r);self.verifyForms[r['id']]=request_fields
    self.completed.append(dep['id']+':'+city['id']+':'+street['id']);self.state.update(departmentIndex=di,cityIndex=ci,streetIndex=si+1)
    if len(self.rows)>=20:break
   if self.state.get('streetIndex',0)>=len(streets):self.state.update(cityIndex=ci+1,streetIndex=0)
   break
  if self.state.get('cityIndex',0)>=len(cities):self.state.update(departmentIndex=(di+1)%len(deps),cityIndex=0,streetIndex=0)
  self.rows=consensus(self.rows)
  # Independently reread each source form used by the selected address sample.
  rereads={}
  for r in random.Random('zhytomyr|coverage').sample(self.rows,min(20,len(self.rows))):
   fields=self.verifyForms[r['id']];key=json.dumps(fields,sort_keys=True)
   if key not in rereads:rereads[key]=form(self.f.text(url,fields)).rows
   values=[]
   for row in rereads[key]:
    if len(row)==7 and locality(row[1])==locality(r['settlement']) and row[2]==r['street'] and r['houses'][0] in houses(row[3]):values.append(row[4]+'.'+row[5] if re.fullmatch('[1-6]',row[4]) and re.fullmatch('[12]',row[5]) else None)
   self.check(r['settlement'],r['street'],r['houses'][0],r['queue'],'confirmed_source_reread' if values and all(v==r['queue'] for v in values) else 'conflict')
 def cherkasy(self):
  api='https://cabinet.cherkasyoblenergo.com/api_new/disconn.php'
  def q(**p):return self.f.json(api+'?'+urllib.parse.urlencode(p))
  vals=lambda x:list(x.values()) if isinstance(x,dict) else x
  branches=vals(q(op='department_list'));bi=self.state.get('branchIndex',0)%len(branches);cities=vals(q(op='city_list',dept_id=branches[bi]['ID']))
  for ci in range(self.state.get('cityIndex',0),min(len(cities),self.state.get('cityIndex',0)+5)):
   city=cities[ci];community=city.get('community') or self.context(city['NAME'])
   if not community:continue
   streets=vals(q(op='street_list',city_id=city['ID'],search_name=''));pool=[]
   for street in streets[:5]:
    for h in vals(q(op='house_list',street_id=street['ID'],search_name='')):pool.append((street,str(h['HOUSE'])))
   random.Random(str(city['ID'])+'|coverage').shuffle(pool)
   for street,house in pool[:30]:
    if self.f.calls>=self.f.budget-10:break
    accounts=vals(q(op='ls_list_by_addr',street_id=street['ID'],house=house))
    if not accounts or len(accounts)>8:continue
    queues=[]
    for account in accounts:
     # These ephemeral identifiers are never written to records, reports or traces.
     data=q(op='disconn_by_ls',disconn_selector='2',n_date=datetime.datetime.now(datetime.timezone.utc).strftime('%d.%m.%Y'),k_date=datetime.datetime.now(datetime.timezone.utc).strftime('%d.%m.%Y'),abon_ls=account['LS']);sections=[clean(v.get('QUEUE_INFO','')) for v in vals(data.get('DISCONN_QUEUQ',{}))]
     values=[]
     for section in sections:
      for part in re.split(r'(?=(?:СГАВ|ГАВ|ГПВ))',section):
       if 'ГПВ' in part or 'погодин' in part.lower():
        values.extend(a+'.'+b for a,b in re.findall(r'([1-6])\s*черг[аиу]\s*[,;:–—-]?\s*([12])\s*підчерг[аиу]',part,re.I));values.extend(a+'.'+b for a,b in re.findall(r'(?<![\d.])([1-6])\s*[.,]\s*([12])(?![\d.])',part))
     queues.append(values[0] if values and len(set(values))==1 else None)
    if queues and all(queues) and len(set(queues))==1:self.add(city['NAME'],community,street['NAME'],house,queues[0],URLS[self.op]);self.check(city['NAME'],street['NAME'],house,queues[0])
   self.state.update(branchIndex=bi,cityIndex=ci+1);return
  self.state.update(branchIndex=(bi+1)%len(branches),cityIndex=0)
 def sumy(self):
  # Protection is reported before a response decoder is invented. No account endpoints.
  data=self.f.json('https://www.soe.com.ua/next-api/shutdowns/cities?search=')
  self.errors.append({'stage':'cities','error':'unimplemented_or_protected_codec','responseShape':list(data) if isinstance(data,dict) else type(data).__name__,'publicWebsiteRoutes':['/next-api/shutdowns/cities','/next-api/shutdowns/streets','/next-api/shutdowns/queues-by-street'],'protocolSource':'https://www.soe.com.ua/consumers/shutdowns'})

def main():
 p=argparse.ArgumentParser();p.add_argument('--operator',required=True,choices=REGIONS);p.add_argument('--output',required=True);p.add_argument('--budget',type=int,default=60);p.add_argument('--state');p.add_argument('--target-city');p.add_argument('--full-city',action='store_true');p.add_argument('--request-limit',type=int);a=p.parse_args()
 budget=a.request_limit if a.request_limit is not None else a.budget
 if not 1<=budget<=5000:raise ValueError('invalid_budget')
 state_path=Path(a.state or 'coverage/batch-a-state-'+a.operator+'.json');states=json.loads(state_path.read_text()) if state_path.exists() else {};c=Collector(a.operator,budget,states.get(a.operator,{}),target_city=a.target_city,full_city=a.full_city);started=int(time.time()*1000)
 try:c.collect_city() if c.full_city else getattr(c,a.operator)()
 except Exception as e:c.error('collection',e)
 c.rows=consensus(c.rows);now=int(time.time()*1000);out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True)
 states[a.operator]=c.state;state_path.parent.mkdir(parents=True,exist_ok=True);state_path.write_text(json.dumps(states,indent=2)+'\n')
 report={'schemaVersion':1,'operatorId':a.operator,'startedAt':started,'finishedAt':now,'records':len(c.rows),'checks':c.checks,'confirmedSampleAddresses':sum(x['status'].startswith('confirmed') for x in c.checks),'sampleMethod':'source-derived address sample; selected before queue queries or independently reread official roster; not Android UI audit','http':c.f.trace,'errors':c.errors,'geography':c.contexts,'nextState':c.state,'traversal':c.traversal,'status':'collected' if c.rows else 'blocked_or_no_confirmed_context'}
 out.with_suffix(out.suffix+'.report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 if not c.rows:print(json.dumps({'operator':a.operator,'records':0,'errors':len(c.errors)}));raise SystemExit(1)
 bundle={'schemaVersion':1,'operatorId':a.operator,'generatedAt':now,'expiresAt':min(r['expiresAt'] for r in c.rows),'records':c.rows,'completedStreetIds':c.completed}
 # Align all rows to this bundle's conservative expiry, without extending observations.
 for r in bundle['records']:r['expiresAt']=min(r['expiresAt'],bundle['expiresAt'])
 out.write_text(json.dumps(bundle,ensure_ascii=False,separators=(',',':'))+'\n');print(json.dumps({'operator':a.operator,'records':len(c.rows),'checks':len(c.checks)}))
if __name__=='__main__':main()
