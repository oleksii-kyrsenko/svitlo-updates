"""Collect a bounded rotating portion of the official legacy ASD public directory.
No subscriber identifiers are persisted; mixed/unknown connections are omitted.
"""
import argparse,datetime,hashlib,json,re,time,urllib.parse,urllib.request
from pathlib import Path
API='https://power-api.loe.lviv.ua/api'
def get(path):
 with urllib.request.urlopen(urllib.request.Request(API+path,headers={'Accept':'application/json','Accept-Language':'uk','User-Agent':'Mozilla/5.0'}),timeout=30) as r:
  raw=r.read(8_000_001)
  if len(raw)>8_000_000:raise ValueError('oversize')
  value=json.loads(raw)
 if isinstance(value,list):return value
 rows=value.get('hydra:member',value.get('member'))
 if not isinstance(rows,list) or value.get('hydra:totalItems',len(rows))>len(rows):raise ValueError('incomplete_directory')
 return rows
def query(path,**values):return get(path+'?'+urllib.parse.urlencode({'pagination':'false',**values}))
def qvalue(value):
 s=str(value).strip()
 if re.fullmatch('[1-6][12]',s):s=s[0]+'.'+s[1]
 return s if re.fullmatch(r'[1-6]\.[12]',s) else None
def records(city,street,rows,now):
 grouped={}
 for row in rows:
  house=str(row.get('buildingName','')).strip()
  if house:grouped.setdefault(house,[]).append(qvalue(row.get('chergGpv','')))
 out=[]
 for house,qs in grouped.items():
  if not all(qs) or len(set(qs))!=1:continue
  queue=qs[0];quote=f"{city['name']}, {street['name']}, буд. {house}: черга {queue}"
  identity=f"{city['id']}:{street['id']}:{house}"
  out.append({'id':hashlib.sha256(identity.encode()).hexdigest()[:24],'regionId':'UA-46','settlement':city['name'],'community':city.get('otg',{}).get('name',''),'street':street['name'],'officialCityId':f"{city['id']}:{street['id']}",'scope':'house','houses':[house],'queue':queue,'sourceUrl':API+'/pw_accounts?'+urllib.parse.urlencode({'pagination':'false','city.id':city['id'],'street.id':street['id']}),'quote':quote,'quoteType':'structured-official-fields','checkedAt':now,'expiresAt':now+24*3600000,'official':True})
 return out

def initial_state():
 return {'schemaVersion':1,'cityIndex':0,'streetIndex':0,'cityId':None,'streetId':None,'consecutiveFailures':0,'cycles':0}
def advance_city(state,total):
 state['cityIndex']=(state['cityIndex']+1)%total
 if state['cityIndex']==0:state['cycles']+=1
 state.update(streetIndex=0,cityId=None,streetId=None,consecutiveFailures=0)
def crawl(cities,state,street_budget=8,city_budget=1,fetch=query,pause=time.sleep,now=None,deadline=None):
 """Persist next city/street, retry failures three times, revisit skipped reads next cycle."""
 now=now or int(time.time()*1000);state={**initial_state(),**state}
 cities=sorted(cities,key=lambda c:str(c['id']));out=[];errors=[];completed=[];examined=0;requests=0
 if not cities:return out,completed,errors,state,examined
 by_id={str(c['id']):i for i,c in enumerate(cities)}
 state['cityIndex']=by_id.get(str(state.get('cityId')),state['cityIndex']%len(cities))
 while examined<city_budget and requests<street_budget and (deadline is None or time.monotonic()<deadline):
  city=cities[state['cityIndex']];state['cityId']=str(city['id']);examined+=1
  try:streets=sorted(fetch('/pw_streets',**{'city.id':city['id']}),key=lambda s:str(s['id']))
  except Exception as e:
   state['consecutiveFailures']+=1;errors.append({'stage':'streets','cityId':city['id'],'error':type(e).__name__,'attempt':state['consecutiveFailures']})
   if state['consecutiveFailures']>=3:advance_city(state,len(cities))
   break
  if not streets:advance_city(state,len(cities));continue
  indexes={str(s['id']):i for i,s in enumerate(streets)}
  state['streetIndex']=indexes.get(str(state.get('streetId')),state['streetIndex'])
  if state['streetIndex']>=len(streets):advance_city(state,len(cities));continue
  while requests<street_budget and state['streetIndex']<len(streets) and (deadline is None or time.monotonic()<deadline):
   street=streets[state['streetIndex']];state['streetId']=str(street['id']);requests+=1
   try:
    rows=fetch('/pw_accounts',**{'city.id':city['id'],'street.id':street['id']})
    out.extend(records(city,street,rows,now));completed.append(f"{city['id']}:{street['id']}");state['consecutiveFailures']=0
   except Exception as e:
    state['consecutiveFailures']+=1;errors.append({'stage':'houses','cityId':city['id'],'streetId':street['id'],'error':type(e).__name__,'attempt':state['consecutiveFailures']})
    if state['consecutiveFailures']<3:break
    # Bounded skip only for this cycle; full wrap revisits the failed street.
    errors[-1]['retryNextCycle']=True;state['consecutiveFailures']=0
   state['streetIndex']+=1
   state['streetId']=str(streets[state['streetIndex']]['id']) if state['streetIndex']<len(streets) else None
   pause(1)
  if state['streetIndex']>=len(streets):advance_city(state,len(cities))
  else:break
 state['updatedAt']=now
 return out,completed,errors,state,examined

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--city-limit',type=int,default=1);p.add_argument('--street-limit',type=int,default=8);p.add_argument('--state',default='coverage/crawl-state.json');p.add_argument('--city-query');a=p.parse_args()
 if not 1<=a.city_limit<=10 or not 1<=a.street_limit<=50:raise ValueError('unbounded request')
 now=int(time.time()*1000);state_file=Path(a.state);state=json.loads(state_file.read_text()) if state_file.exists() else initial_state()
 if state.get('schemaVersion')!=1 or any(not isinstance(state.get(k,0),int) or state.get(k,0)<0 for k in ['cityIndex','streetIndex','consecutiveFailures','cycles']):raise ValueError('invalid_cursor')
 cities=query('/pw_cities',**({'name':a.city_query} if a.city_query else {}))
 found,completed,errors,state,examined=crawl(cities,state,a.street_limit,a.city_limit,now=now,deadline=time.monotonic()+480)
 # Atomic cursor update is separate from publication; no source timestamps are extended.
 state_file.parent.mkdir(parents=True,exist_ok=True);temp=state_file.with_suffix('.tmp');temp.write_text(json.dumps(state,indent=2)+'\n');temp.replace(state_file)
 report={'checkedAt':now,'citiesExamined':examined,'records':len(found),'errors':errors,'completedStreetIds':completed,'nextCursor':state,'method':'official-directory-harvest-not-independent-address-audit'}
 Path(a.output).parent.mkdir(parents=True,exist_ok=True);Path(a.output+'.report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 if not completed:raise SystemExit('No complete street reads; previous bundle preserved; cursor retry saved')
 bundle={'schemaVersion':1,'operatorId':'lviv','generatedAt':now,'expiresAt':now+24*3600000,'records':found,'completedStreetIds':completed}
 Path(a.output).write_text(json.dumps(bundle,ensure_ascii=False,separators=(',',':'))+'\n')
 print(json.dumps({'records':len(found),'errors':len(errors),'completedStreetLists':len(completed),'nextCursor':state}))
if __name__=='__main__':main()
