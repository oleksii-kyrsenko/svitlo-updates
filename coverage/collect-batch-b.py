"""Standalone, bounded public-source collectors. No application implementation imported.
Fresh official community context is mandatory. Only public address/queue facts survive.
"""
import argparse,hashlib,html,json,re,time,urllib.error,urllib.parse,urllib.request
from pathlib import Path
CONFIG={
 'ternopil':('UA-61','https://api-poweron.toe.com.ua/api'),
 'zakarpattia':('UA-21','https://api-outage-zakarpat-energy.inneti.net/api'),
 'vinnytsia':('UA-05','https://www.voe.com.ua/disconnection/detailed'),
 'volyn':('UA-07','https://www.energy.volyn.ua/spozhyvacham/perervy-u-elektropostachanni/cherga/'),
 'prykarpattia':('UA-26','https://svitlo.oe.if.ua/'),
 'kirovohrad':('UA-35','https://kiroe.com.ua/electricity-blackout'),
 'khmelnytskyi':('UA-68','https://hoe.com.ua/shutdown/queue')}
def now():return int(time.time()*1000)
def queue(value):
 value=str(value or '').strip()
 if re.fullmatch('[1-6][12]',value):value=value[0]+'.'+value[1]
 return value if re.fullmatch(r'[1-9]\d?(?:\.\d{1,2})?',value) else None
def consensus(values):
 values=[queue(x) for x in values]
 return values[0] if values and all(values) and len(set(values))==1 else None
def rows(value):
 if isinstance(value,list):return value
 if not isinstance(value,dict):raise ValueError('unsupported_list')
 result=value.get('hydra:member',value.get('member'))
 if not isinstance(result,list) or value.get('hydra:totalItems',len(result))>len(result):raise ValueError('incomplete_list')
 return result
def clean_house(value):
 value=str(value or '').strip()
 return value if re.fullmatch(r'\d+[А-Яа-яІіЇїЄєҐґA-Za-z]?(?:[/-][\dА-Яа-яІіЇїЄєҐґA-Za-z]+)?',value) else None
def houselist(value):return [h for x in str(value or '').split(',') if (h:=clean_house(x))]
class HTTP:
 def __init__(self):self.last=0;self.observations=[];self.cache={}
 def get(self,url,data=None):
  key=(url,json.dumps(data,sort_keys=True))
  if key in self.cache:return self.cache[key]
  time.sleep(max(0,1-(time.monotonic()-self.last)));self.last=time.monotonic()
  request=urllib.request.Request(url,data=urllib.parse.urlencode(data).encode() if data is not None else None,headers={'User-Agent':'Svitlo-public-coverage/1.0 (+https://github.com/oleksii-kyrsenko/svitlo-updates)','Accept':'application/json,text/html','Accept-Language':'uk',**({'Content-Type':'application/x-www-form-urlencoded','X-Requested-With':'XMLHttpRequest'} if data is not None else {})})
  observed={'url':url,'method':'POST' if data is not None else 'GET','checkedAt':now()}
  try:
   with urllib.request.urlopen(request,timeout=20) as response:
    value=response.read(8_000_001);observed.update(status=response.status,bytes=len(value))
    if len(value)>8_000_000:raise ValueError('oversize')
    self.cache[key]=value
    return value
  except urllib.error.HTTPError as error:observed.update(status=error.code,reason='protected' if error.code in (401,403,429) else 'http_error');raise
  except Exception as error:observed.update(reason=type(error).__name__);raise
  finally:self.observations.append(observed)
 def json(self,url,data=None):return json.loads(self.get(url,data))
def url(base,path,**values):return base+path+'?'+urllib.parse.urlencode({'pagination':'false',**values})
def make_record(operator,region,city,street,house,q,source,observed):
 community=(city.get('otg') or {}).get('name')
 if not community or not city.get('name') or not street.get('name') or not clean_house(house) or not queue(q):return None
 identity=':'.join([operator,str(city['id']),str(street['id']),house])
 return {'id':hashlib.sha256(identity.encode()).hexdigest()[:24],'official':True,'regionId':region,'settlement':city['name'],'community':community,'street':street['name'],'officialCityId':f"{city['id']}:{street['id']}",'scope':'house','houses':[house],'queue':q,'sourceUrl':source,'quote':f"{city['name']}, {street['name']}, буд. {house}: черга {q}",'quoteType':'structured-official-fields','checkedAt':observed,'expiresAt':observed+86400000}
def collect_asd(operator,http,state,city_limit,street_limit):
 region,base=CONFIG[operator];cities=rows(http.json(url(base,'/pw_cities')))
 cities=sorted([c for c in cities if isinstance(c,dict) and c.get('id') and (c.get('otg') or {}).get('name')],key=lambda c:int(c['id']))
 records=[];checks=[];completed=[];errors=[];used=0
 if not cities:return records,checks,completed,[{'reason':'no_official_community_context'}]
 index=int(state.get('cityIndex',0))%len(cities)
 for offset in range(min(city_limit,len(cities))):
  city=cities[(index+offset)%len(cities)]
  try:streets=sorted(rows(http.json(url(base,'/pw_streets',**{'city.id':city['id']}))),key=lambda s:int(s['id']))
  except Exception as e:errors.append({'stage':'streets','cityId':city['id'],'reason':type(e).__name__});continue
  start=int(state.get('streetIndex',0)) if offset==0 else 0
  for si in range(start,len(streets)):
   if used>=street_limit or len(checks)>=20:break
   used+=1;street=streets[si];context=f"{city['id']}:{street['id']}"
   try:
    if operator=='ternopil':
     names=http.json(base+'/pw-accounts/building-names?'+urllib.parse.urlencode({'cityId':city['id'],'streetId':street['id']}))
     if not isinstance(names,dict) or not isinstance(names.get('buildingNames'),list):raise ValueError('invalid_building_names')
     houses=sorted({h for row in names['buildingNames'] if isinstance(row,dict) and (h:=clean_house(row.get('buildingName')))},key=lambda h:hashlib.sha256((context+':'+h).encode()).hexdigest())
    else:
     discovered=rows(http.json(url(base,'/pw_address_queues',**{'city.id':city['id'],'street.id':street['id']})))
     houses=sorted({h for row in discovered for h in houselist(row.get('buildingNames'))},key=lambda h:hashlib.sha256((context+':'+h).encode()).hexdigest())
    # Select from source address names, independently of queue value or success.
    take=min(5,20-len(checks),len(houses));offset=int(state.setdefault('houseOffsets',{}).get(context,0))%max(1,len(houses))
    selected=(houses[offset:]+houses[:offset])[:take]
    state['houseOffsets'][context]=(offset+take)%max(1,len(houses))
    for house in selected:
     source=base+'/pw-accounts/building-groups?'+urllib.parse.urlencode({'cityId':city['id'],'streetId':street['id'],'buildingNames':house}) if operator=='ternopil' else url(base,'/pw_address_queues',**{'city.id':city['id'],'street.id':street['id'],'buildingNames':house})
     try:
      response=http.json(source)
      if operator=='ternopil':
       if not isinstance(response,dict) or not isinstance(response.get('buildingGroups'),list):raise ValueError('invalid_building_groups')
       matches=response['buildingGroups']
      else:
       matches=[r for r in rows(response) if house in houselist(r.get('buildingNames')) and str((r.get('city') or {}).get('id'))==str(city['id']) and str((r.get('street') or {}).get('id'))==str(street['id'])]
      q=consensus(r.get('chergGpv') for r in matches);observed=now()
      checks.append({'settlement':city['name'],'community':city['otg']['name'],'street':street['name'],'house':house,'status':'ready' if q else 'unconfirmed','queue':q,'sourceUrl':source,'checkedAt':observed})
      if q:
       record=make_record(operator,region,city,street,house,q,source,observed)
       if record:records.append(record)
     except Exception as e:checks.append({'settlement':city['name'],'street':street['name'],'house':house,'status':'source_failed','reason':type(e).__name__,'sourceUrl':source})
    # This is a bounded house sample, not a complete street snapshot.
   except Exception as e:errors.append({'stage':'houses','cityId':city['id'],'streetId':street['id'],'reason':type(e).__name__})
   state.update(cityIndex=(index+offset)%len(cities),streetIndex=si+1)
  if used>=street_limit or len(checks)>=20:break
  state.update(cityIndex=(index+offset+1)%len(cities),streetIndex=0)
 return records,checks,completed,errors

def probe_other(operator,http):
 _,base=CONFIG[operator];page=http.get(base).decode('utf-8','replace')
 if operator=='khmelnytskyi':http.get('https://hoe.com.ua/settlements?term=');return 'settlement_enumeration_requires_supported_format'
 if operator=='kirovohrad':
  token=re.search(r'ajaxToken:\s*[\"\']([^\"\']+)',page);select=re.search(r'<select[^>]*id=[\"\']fn_office[\"\'][^>]*>(.*?)</select>',page,re.S)
  offices=re.findall(r'<option[^>]*value=[\"\'](\d+)[\"\'][^>]*>([^<]+)',select.group(1) if select else '')
  if not token or not offices:return 'official_otg_directory_missing'
  http.json(base+'/city/'+offices[0][0],{'ajax':1,'token':token.group(1)});return 'city_response_requires_supported_format'
 return 'public_freeform_lookup_requires_geographic_address_discovery'
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--operator',required=True,choices=CONFIG);parser.add_argument('--output',required=True);parser.add_argument('--state');parser.add_argument('--street-limit',type=int,default=4);parser.add_argument('--city-limit',type=int,default=3);args=parser.parse_args()
 if not 1<=args.street_limit<=20 or not 1<=args.city_limit<=10:raise ValueError('unbounded_budget')
 out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True);statefile=Path(args.state) if args.state else out.with_suffix('.state.json');state=json.loads(statefile.read_text()) if statefile.exists() else {'schemaVersion':1,'cityIndex':0,'streetIndex':0}
 http=HTTP();records=[];checks=[];completed=[];errors=[]
 try:
  if args.operator in ('ternopil','zakarpattia'):records,checks,completed,errors=collect_asd(args.operator,http,state,args.city_limit,args.street_limit)
  else:errors.append({'reason':probe_other(args.operator,http)})
 except Exception as error:errors.append({'reason':type(error).__name__})
 generated=now();state['updatedAt']=generated;statefile.write_text(json.dumps(state,indent=2)+'\n')
 report={'operatorId':args.operator,'checkedAt':generated,'records':len(records),'addressChecks':checks,'sampleMethod':'up-to20 queue-blind hash-selected official address names; up-to5 perstreet; independent followup queue request; not nationwide random coverage','completedStreetIds':completed,'requests':http.observations,'errors':errors,'status':'collected' if records else 'blocked_or_unresolved'}
 Path(str(out)+'.report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 if not records:raise SystemExit('No verified records; previous output preserved; see report')
 bundle={'schemaVersion':1,'operatorId':args.operator,'generatedAt':generated,'expiresAt':generated+86400000,'records':records,'completedStreetIds':completed}
 out.write_text(json.dumps(bundle,ensure_ascii=False,separators=(',',':'))+'\n');print(json.dumps({'operatorId':args.operator,'records':len(records),'checks':len(checks)}))
if __name__=='__main__':main()
