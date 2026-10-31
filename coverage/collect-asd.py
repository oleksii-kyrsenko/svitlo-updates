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

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--city-limit',type=int,default=1);p.add_argument('--street-limit',type=int,default=8);p.add_argument('--offset',type=int,default=0);p.add_argument('--city-query');a=p.parse_args()
 if not 1<=a.city_limit<=10 or not 1<=a.street_limit<=50:raise ValueError('unbounded request')
 now=int(time.time()*1000);cities=query('/pw_cities',**({'name':a.city_query} if a.city_query else {}));records_all=[];errors=[];completed=[]
 cities=sorted(cities,key=lambda c:str(c.get('id','')));selected=cities[a.offset%len(cities):][:a.city_limit]
 for city in selected:
  try:streets=query('/pw_streets',**{'city.id':city['id']})
  except Exception as e:errors.append({'stage':'streets','error':type(e).__name__});continue
  for street in streets[:a.street_limit]:
   try:
    rows=query('/pw_accounts',**{'city.id':city['id'],'street.id':street['id']});records_all.extend(records(city,street,rows,now));completed.append(f"{city['id']}:{street['id']}")
   except Exception as e:errors.append({'stage':'houses','cityId':city['id'],'streetId':street['id'],'error':type(e).__name__})
   time.sleep(1)
 bundle={'schemaVersion':1,'operatorId':'lviv','generatedAt':now,'expiresAt':now+24*3600000,'records':records_all,'completedStreetIds':completed}
 if not completed:
  Path(a.output+'.report.json').parent.mkdir(parents=True,exist_ok=True);Path(a.output+'.report.json').write_text(json.dumps({'checkedAt':now,'records':0,'errors':errors,'previousBundlePreserved':True},ensure_ascii=False,indent=2)+'\n');raise SystemExit('No confirmed records; previous bundle preserved')
 Path(a.output).parent.mkdir(parents=True,exist_ok=True);Path(a.output).write_text(json.dumps(bundle,ensure_ascii=False,separators=(',',':'))+'\n')
 Path(a.output+'.report.json').write_text(json.dumps({'checkedAt':now,'citiesExamined':len(selected),'records':len(records_all),'errors':errors,'method':'official-directory-harvest-not-independent-address-audit'},ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'records':len(records_all),'errors':len(errors)}))
 if not records_all:raise SystemExit('No confirmed records; preserve previous signed manifest')
if __name__=='__main__':main()
