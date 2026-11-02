"""Public YASNO/DTEK source collector. No app code or subscriber data is used.
Dictionary IDs and labels are discovered at runtime; bounded cursor batches are partial coverage.
"""
import argparse,hashlib,http.cookiejar,json,re,subprocess,sys,time,urllib.parse,urllib.request
from pathlib import Path
from city_crawl import RequestLimit,select_city,scoped_state,request_limit,crawl_report,search_inventory
API='https://app.yasno.ua/api/blackout-service/public/shutdowns/addresses/v2/'
CONFIG={'dtek-kyiv':(25,902,'UA-30'),'dtek-dnipro':(3,301,'UA-12'),'cek':(3,303,'UA-12')}
DTEK={'dtek-kyiv-region':'www.dtek-krem.com.ua','dtek-odesa':'www.dtek-oem.com.ua','dtek-donetsk':'www.dtek-dem.com.ua','dtek-pem':'www.dtek-pem.com.ua','dtek-vvm':'www.dtek-vvm.com.ua'}
def dtek_page_url(operator):
 return 'https://'+DTEK[operator]+('/ua/shutdowns-schedule' if operator in ('dtek-pem','dtek-vvm') else '/ua/shutdowns')
class Client:
 def __init__(self,limit=2000):self.limit=limit;self.opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()));self.requests=0;self.observations=[]
 def read(self,url,data=None):
  if self.requests>=self.limit:raise RequestLimit('request_limit')
  from request_budget import throttle
  throttle(url)
  self.requests+=1
  req=urllib.request.Request(url,data=data,headers={'User-Agent':'Mozilla/5.0 (public electricity coverage research)','Accept':'application/json,text/html','Accept-Language':'uk',**({'Content-Type':'application/x-www-form-urlencoded','X-Requested-With':'XMLHttpRequest'} if data else {})})
  try:
   with self.opener.open(req,timeout=20) as r:b=r.read(8_000_001);status=r.status
   if len(b)>8_000_000:raise ValueError('oversize')
   text=b.decode('utf-8');self.observations.append({'url':url,'httpStatus':status,'bytes':len(b),'responseSha256':hashlib.sha256(b).hexdigest(),'checkedAt':int(time.time()*1000)})
   if re.search('_Incapsula_Resource|cf-chl-|Just a moment',text) and 'DisconSchedule.streets' not in text:raise ValueError('source_protected_http_200')
   return text
  except Exception as e:
   self.observations.append({'url':url,'error':str(e)[:180],'checkedAt':int(time.time()*1000)});raise
 def query(self,path,params):
  url=API+path+'?'+urllib.parse.urlencode(params);return json.loads(self.read(url)),url

def city_order(name):
 value=str(name).strip().casefold()
 return 0 if re.match(r'^м\.\s*',value) else 1 if re.match(r'^(?:смт|селище)',value) else 2

def qvalue(v):
 if isinstance(v,dict):
  group=str(v.get('group',''));sub=v.get('subgroup',0) or 0
  if not re.fullmatch(r'[1-9]\d?',group) or not isinstance(sub,int) or not 0<=sub<=99:return None
  return group+(f'.{sub}' if sub else '')
 return str(v) if re.fullmatch(r'[1-9]\d?(?:\.\d{1,2})?',str(v)) else None

def source_record(city,street,house,queue,operator,region,community,url,now):
 identity=f"{operator}:{city.get('id','')}:{street['id']}:{house['id']}"
 return {'id':hashlib.sha256(identity.encode()).hexdigest()[:24],'official':True,'regionId':region,'settlement':city['value'],'community':community,'street':street['value'],**({'providerCityId':str(city['id'])} if city.get('id') is not None else {}),'providerStreetId':str(street['id']),'scope':'house','houses':[house['value']],'queue':queue,'sourceUrl':url,'quote':f"{city['value']}, {street['value']}, буд. {house['value']}: черга {queue}",'quoteType':'structured-official-fields','checkedAt':now,'expiresAt':now+24*3600000}

def resolve(city,region,state):
 key=region+'|'+city;cache=state.setdefault('contexts',{});saved=cache.get(key)
 if saved and saved.get('checkedAt',0)>int(time.time()*1000)-86400000:return saved
 helper=Path(__file__).with_name('geography.py')
 if not helper.exists():return {'status':'unresolved','reason':'geography_helper_unavailable'}
 p=subprocess.run([sys.executable,str(helper)],input=json.dumps({'settlement':city,'regionId':region})+'\n',capture_output=True,text=True,timeout=45)
 if p.returncode:return {'status':'unresolved','reason':'geography_helper_failed'}
 result=json.loads(p.stdout.strip().splitlines()[-1]);cache[key]=result;return result

def yasno(operator,state,budget,client,resolver=resolve,now=None,target_city=None,full_city=False):
 if full_city:return yasno_city(operator,state,budget,client,resolver,now,target_city)
 now=now or int(time.time()*1000);rid,dso,region=CONFIG[operator];params={'regionId':rid,'dsoId':dso};out=[];errors=[];completed=[];checked=0;deadline=time.monotonic()+150
 metadata,_=client.query('regions',{});area=next((r for r in metadata if r['id']==rid and any(d['id']==dso for d in r['dsos'])),None)
 if not area:raise ValueError('operator_missing_official_registry')
 cities,_=client.query('cities',{**params,'query':''}) if area['hasCities'] else ([{'value':area['value']}],None)
 if not isinstance(cities,list) or not cities:raise ValueError('empty_city_dictionary')
 cities=select_city(cities,target_city,'value')
 cities=sorted(cities,key=lambda c:(city_order(c.get('value')),int(c.get('id',0))));ci=state.get('cityIndex',0)%len(cities);city=cities[ci]
 context=resolver(city['value'],region,state)
 if context.get('status')!='resolved':errors.append({'stage':'context','settlement':city['value'],'reason':context.get('reason','unresolved')})
 state['auditSamples']=[]
 if city.get('id') is not None:params['cityId']=city['id']
 alphabet='абвгґдеєжзиіїйклмнопрстуфхцчшщьюя';queries=['вул','пров','просп','бул']+['вул. '+c for c in alphabet]
 qi=state.get('queryIndex',0)%len(queries);streets,_=client.query('streets',{**params,'query':queries[qi]})
 if not isinstance(streets,list):raise ValueError('invalid_street_dictionary')
 si=state.get('streetIndex',0)
 while si<len(streets) and checked<budget and time.monotonic()<deadline:
  street=streets[si];streetparams={**params,'streetId':street['id']};houses,_=client.query('houses',{**streetparams,'query':''})
  if not isinstance(houses,list):raise ValueError('invalid_house_dictionary')
  hi=state.get('houseIndex',0);counts={}
  for h in houses:counts[h['value'].strip().casefold()]=counts.get(h['value'].strip().casefold(),0)+1
  while hi<len(houses) and checked<budget and time.monotonic()<deadline:
   house=houses[hi];hi+=1;checked+=1
   if counts[house['value'].strip().casefold()]!=1:continue
   try:
    value,url=client.query('group',{**streetparams,'houseId':house['id']});queue=qvalue(value)
    if queue:
     state['auditSamples'].append({'settlement':city['value'],'street':street['value'],'house':house['value'],'queue':queue,'sourceUrl':url,'checkedAt':now})
     if context.get('status')=='resolved':out.append(source_record(city,street,house,queue,operator,region,context['community'],url,now))
    else:errors.append({'stage':'queue','reason':'ambiguous_or_unknown','streetId':street['id'],'house':house['value']})
   except Exception as e:hi-=1;errors.append({'stage':'queue','reason':str(e)[:180]});break
   time.sleep(.2)
  state['houseIndex']=hi
  if hi>=len(houses):completed.append(str(city.get('id',''))+':'+str(street['id']));si+=1;state['houseIndex']=0
  else:break
 state['streetIndex']=si
 if si>=len(streets):
  state.update(streetIndex=0,houseIndex=0,queryIndex=(qi+1)%len(queries))
  if state['queryIndex']==0:state['cityIndex']=(ci+1)%len(cities)
 if context.get('status')!='resolved':state.update(cityIndex=(ci+1)%len(cities),streetIndex=0,houseIndex=0,queryIndex=0)
 state['lastContext']=context
 return out,completed,errors,checked

def house_base(value):
 # A connection selector is not a different building. Only explicit input labels
 # are removable; letters, corps and fractions remain part of the house identity.
 text=str(value or '').strip()
 text=re.sub(r'\s+(?:ввод|ввід)\s*\d+\s*$', '', text, flags=re.I)
 return text if re.fullmatch(r'\d+[А-Яа-яІіЇїЄєҐґA-Za-z]?(?:[/-][\dА-Яа-яІіЇїЄєҐґA-Za-z]+)?',text) else None


def yasno_city(operator,state,budget,client,resolver=resolve,now=None,target_city=None):
 now=now or int(time.time()*1000);rid,dso,region=CONFIG[operator];params={'regionId':rid,'dsoId':dso};out=[];errors=[];checked=0;completed=[];deadline=time.monotonic()+480
 metadata,_=client.query('regions',{})
 area=next((r for r in metadata if r.get('id')==rid and any(d.get('id')==dso for d in r.get('dsos',[]))),None)
 if not area:raise ValueError('operator_missing_official_registry')
 cities,_=client.query('cities',{**params,'query':''}) if area['hasCities'] else ([{'value':area['value']}],None)
 if not isinstance(cities,list) or not cities:raise ValueError('empty_city_dictionary')
 cities=select_city(cities,target_city,'value');ci=int(state.get('cityIndex',0))%len(cities);city=cities[ci]
 if city.get('id') is not None:params['cityId']=city['id']
 context=resolver(city['value'],region,state);state['lastContext']=context;state['auditSamples']=[];state['observedHouses']=[]
 if context.get('status')!='resolved':return [],[],[{'stage':'context','settlement':city['value'],'reason':context.get('reason','unresolved')}],0
 # YASNO's street endpoint requires >=3 characters and returns at most20rows.
 # Cover all supported source street types and expand saturated searches. The
 # source does not expose a full-dictionary contract, so no full-city claim.
 letters='абвгґдеєжзиіїйклмнопрстуфхцчшщьюя0123456789'
 seeds=[prefix+c for prefix in ('вул. ','вулиця ','пров. ','провулок ','просп. ','проспект ','бульв. ','бул. ','бульвар ','пл. ','площа ','узвіз ','наб. ','набережна ','шосе ','дорога ','алея ','тупик ') for c in letters]
 inventory=state.setdefault('streetInventory',{});state['dictionaryComplete']=False;state['inventoryMethod']='source-limited-autocomplete-min3-cap20'
 try:
  streets=search_inventory(lambda term:client.query('streets',{**params,'query':term})[0],inventory,cap=20,initial_queries=seeds,max_queries=max(1,min(40,getattr(client,'limit',200)//8)))
 except Exception as error:
  errors.append({'stage':'street_inventory','reason':type(error).__name__});streets=list(inventory.get('items',{}).values())
 state['inventoryPendingQueries']=len(inventory.get('queries',[]));processed=state.setdefault('processedStreetIds',[])
 for street in sorted(streets,key=lambda s:int(s['id'])):
  if time.monotonic()>=deadline or checked>=budget:break
  key=str(street['id'])
  if key in processed:continue
  streetparams={**params,'streetId':street['id']};hi=state.setdefault('houseInventories',{}).setdefault(key,{})
  try:
   houses=search_inventory(lambda term:client.query('houses',{**streetparams,'query':term})[0],hi,cap=20,initial_queries=['']+list('0123456789'),max_queries=max(1,min(12,getattr(client,'limit',200)//10)))
  except Exception as error:
   errors.append({'stage':'house_inventory','streetId':street['id'],'reason':type(error).__name__});houses=list(hi.get('items',{}).values())
  candidates=sorted({base for h in houses if (base:=house_base(h['value']))});done=state.setdefault('checkedHouses',{}).setdefault(key,[]);failed=False
  for house in candidates:
   if house in done:continue
   if time.monotonic()>=deadline or checked>=budget:break
   try:
    matches,_=client.query('houses',{**streetparams,'query':house})
    if not isinstance(matches,list):raise ValueError('invalid_house_dictionary')
    # A capped result cannot prove that all connections of this building were
    # returned. Wait for a verified exact dictionary rather than choose first.
    if len(matches)>=20:
     errors.append({'stage':'house_identity','streetId':street['id'],'house':house,'reason':'capped_connection_search'});continue
    matches=[h for h in matches if isinstance(h,dict) and house_base(h.get('value'))==house]
    if not matches:continue
    qs=[];source=None
    for h in matches:
     value,source=client.query('group',{**streetparams,'houseId':h['id']});qs.append(qvalue(value))
    checked+=1;q=qs[0] if qs and all(qs) and len(set(qs))==1 else None;observed=int(time.time()*1000)
    state['observedHouses'].append({'regionId':region,'settlement':city['value'],'community':context['community'],'street':street['value'],'house':house,'providerStreetId':str(street['id'])})
    state['auditSamples'].append({'settlement':city['value'],'street':street['value'],'house':house,'queue':q,'status':'ready' if q else 'unconfirmed','sourceUrl':source,'checkedAt':observed})
    done.append(house)
    if q:out.append(source_record(city,street,{'id':house,'value':house},q,operator,region,context['community'],source,observed))
   except Exception as error:
    errors.append({'stage':'queue','streetId':street['id'],'house':house,'reason':type(error).__name__});failed=True;break
  if not failed and not hi.get('queries') and not hi.get('unexpanded') and all(h in done for h in candidates):processed.append(key)
  if failed:break
 state['crawlStatus']='partial'
 # A finished source-search cycle is deliberately not called complete city.
 if not inventory.get('queries') and len(processed)==len(streets):state.update(crawlStatus='source_search_exhausted',streetInventory={},houseInventories={},checkedHouses={},processedStreetIds=[],cityIndex=(ci+1)%len(cities))
 return out,completed,errors,checked


def assignment(text,label):
 match=re.search(re.escape(label)+r'\s*=\s*',text)
 if not match:raise ValueError('missing_'+label)
 return json.JSONDecoder().raw_decode(text[match.end():])[0]

def dtek(operator,client,state,budget,resolver=resolve,now=None,target_city=None,full_city=False):
 now=now or int(time.time()*1000);url=dtek_page_url(operator);text=client.read(url);streets=assignment(text,'DisconSchedule.streets')
 if not isinstance(streets,dict) or not streets:raise ValueError('empty_city_dictionary')
 cities=sorted([c for c,s in streets.items() if isinstance(s,list) and s],key=lambda c:(city_order(c),c))
 if target_city:cities=[row['name'] for row in select_city([{'name':c} for c in cities],target_city)]
 state['dictionaryComplete']=True
 ci=state.get('cityIndex',0)%len(cities);city=cities[ci];items=streets[city]
 region={'dtek-kyiv-region':'UA-32','dtek-odesa':'UA-51','dtek-donetsk':'UA-14','dtek-pem':'UA-14','dtek-vvm':'UA-14'}[operator]
 context=resolver(city,region,state);state['lastContext']=context;state['auditSamples']=[];state['observedHouses']=[];errors=[];out=[];completed=[];checked=0
 if context.get('status')!='resolved':errors.append({'stage':'context','settlement':city,'reason':context.get('reason','unresolved')})
 token=re.search(r'<meta\b[^>]*name=["\']csrf-token["\'][^>]*content=["\']([^"\']+)',text)
 param=re.search(r'<meta\b[^>]*name=["\']csrf-param["\'][^>]*content=["\']([^"\']+)',text)
 try:update=assignment(text,'DisconSchedule.fact').get('update','')
 except ValueError:update=''
 si=state.get('streetIndex',0);deadline=time.monotonic()+480
 while si<len(items) and checked<budget and time.monotonic()<deadline:
  body={'method':'getHomeNum','data[0][name]':'city','data[0][value]':city,'data[1][name]':'street','data[1][value]':items[si],'data[2][name]':'updateFact','data[2][value]':update}
  if token:body[param.group(1) if param else '_csrf']=token.group(1)
  source='https://'+DTEK[operator]+'/ua/ajax';response=json.loads(client.read(source,urllib.parse.urlencode(body).encode()))
  if response.get('result') is not True or not isinstance(response.get('data'),dict):raise ValueError('invalid_house_response')
  houses=sorted(response['data'].items());hi=state.get('houseIndex',0);start_hi=hi
  while hi<len(houses) and checked<budget:
   name,data=houses[hi];hi+=1;checked+=1
   if context.get('status')=='resolved':state['observedHouses'].append({'regionId':region,'settlement':city,'community':context['community'],'street':items[si],'house':name,'providerStreetId':items[si]})
   groups=data.get('sub_type_reason')
   qs=[re.fullmatch(r'GPV([1-9]\d?(?:\.\d{1,2})?)',g) for g in groups] if isinstance(groups,list) else []
   if not qs or not all(qs) or len({q.group(1) for q in qs})!=1:continue
   queue=qs[0].group(1);state['auditSamples'].append({'settlement':city,'street':items[si],'house':name,'queue':queue,'sourceUrl':source,'checkedAt':now})
   if context.get('status')=='resolved':
    # A city value is not a street identity in the normalized client protocol.
    # City/street/house still form the stable record id and quoted provenance.
    out.append(source_record({'id':city,'value':city},{'id':items[si],'value':items[si]},{'id':name,'value':name},queue,operator,region,context['community'],source,now))
  state['houseIndex']=hi
  if hi>=len(houses):
   if start_hi==0:completed.append(city+':'+items[si])
   si+=1;state['houseIndex']=0
  else:break
  time.sleep(.3)
 state['streetIndex']=si
 if si>=len(items):state.update(cityIndex=(ci+1)%len(cities),streetIndex=0,houseIndex=0,crawlStatus='complete')
 else:state['crawlStatus']='partial'
 return out,completed,errors,checked

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--operator',required=True,choices=list(CONFIG)+list(DTEK));ap.add_argument('--output',required=True);ap.add_argument('--state');ap.add_argument('--budget',type=int,default=20);ap.add_argument('--target-city');ap.add_argument('--full-city',action='store_true');ap.add_argument('--request-limit',type=request_limit,default=200);args=ap.parse_args();now=int(time.time()*1000);client=Client(args.request_limit);saved={}
 if args.state and Path(args.state).exists():saved=json.loads(Path(args.state).read_text())
 operator_state=saved.setdefault(args.operator,{}) if 'operators' not in saved else saved['operators'].setdefault(args.operator,{})
 state=scoped_state(operator_state,args.target_city,args.full_city);state['crawlStatus']='partial';state['observedHouses']=[]
 extra={'target_city':args.target_city,'full_city':args.full_city} if args.target_city or args.full_city else {}
 try:records,completed,errors,checked=yasno(args.operator,state,100000 if args.full_city else max(1,min(args.budget,100)),client,**extra) if args.operator in CONFIG else dtek(args.operator,client,state,100000 if args.full_city else max(1,min(args.budget,100)),**extra)
 except Exception as e:records,completed,errors,checked=[],[],[{'stage':'collection','reason':str(e)[:180]}],0
 finished=int(time.time()*1000)
 deadline=max((r['expiresAt'] for r in records),default=finished+86400000)
 report={'schemaVersion':1,'operatorId':args.operator,'generatedAt':finished,'expiresAt':deadline,'records':records,'completedStreetIds':completed,'observedHouses':state.get('observedHouses',[]),'errors':errors,'checkedAddresses':checked,'requestCount':client.requests,'observations':client.observations,'context':state.get('lastContext'),'auditSamples':state.get('auditSamples',[]),'cityCrawl':crawl_report(state,args.target_city,args.full_city)}
 Path(args.output).parent.mkdir(parents=True,exist_ok=True);Path(args.output+'.report.json').write_text(json.dumps({**report,'records':len(records),'constraint':None if records else 'no-verified-geographic-context-or-source-data'},ensure_ascii=False,indent=2)+'\n')
 if records or report['observedHouses']:Path(args.output).write_text(json.dumps({k:report[k] for k in ['schemaVersion','operatorId','generatedAt','expiresAt','records','completedStreetIds','observedHouses']},ensure_ascii=False,separators=(',',':'))+'\n')
 if args.state:
  p=Path(args.state);saved.setdefault('operators',{})[args.operator]=operator_state;p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(saved,ensure_ascii=False,indent=2)+'\n');tmp.replace(p)
 print(json.dumps({'operatorId':args.operator,'records':len(records),'checkedAddresses':checked,'errors':errors[:3]},ensure_ascii=False))
 if not records and not report['observedHouses']:raise SystemExit(2)
if __name__=='__main__':main()
