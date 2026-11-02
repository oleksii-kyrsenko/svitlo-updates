"""Collect only geographic holdout candidates; never import queue sources.

Original map candidates may be supplied as an archive to avoid repeating bulk
requests. Exact OSM buildings are verified by bounded Nominatim lookup batches.
"""
import argparse,hashlib,json,math,pathlib,re,sys,time,urllib.parse,urllib.request,zipfile
from datetime import datetime,timezone
from common import canonical,digest,distance_km,read_json,street_identity,write_json
from holdout import generate
HEADER={'User-Agent':'KolySvitloQA/1.0 (+https://github.com/oleksii-kyrsenko/svitlo-updates; geographic sample)'}
def request(url,body=None):
 req=urllib.request.Request(url,data=body,headers=HEADER)
 with urllib.request.urlopen(req,timeout=75) as r:
  raw=r.read(16_000_001)
  if len(raw)>16_000_000:raise ValueError('geographic_response_limit')
  return raw

def fetch_map(city):
 query='[out:json][timeout:50];area('+str(3600000000+city['cityOsmRelation'])+')->.a;nwr["building"~"^(house|apartments|residential|detached|semidetached_house|terrace)$"]["addr:street"]["addr:housenumber"](area.a);out tags center;'
 errors=[]
 for server in ['https://overpass-api.de/api/interpreter','https://overpass.kumi.systems/api/interpreter']:
  try:return request(server,urllib.parse.urlencode({'data':query}).encode())
  except Exception as e:errors.append(str(e))
 raise ValueError('map_unavailable: '+repr(errors))

def bounded_map(city, cases, evidence):
 """Ordinary OSM map windows when the aggregate Overpass service fails."""
 import gzip,xml.etree.ElementTree as ET
 sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
 from request_budget import throttle
 center={'latitude':city['centerLatitude'],'longitude':city['centerLongitude']}
 extent=max(distance_km(c,center) for c in cases)
 radius=max(2.5,min(7,extent*.72));elements={};errors=[]
 def read_box(bbox,label,split=False):
  url='https://api.openstreetmap.org/api/0.6/map?bbox='+','.join(f'{v:.6f}' for v in bbox)
  target=evidence/(city['regionId']+f'-window-{label}.osm.gz');meta=evidence/(target.name+'.meta.json')
  try:
   if target.exists():raw=gzip.decompress(target.read_bytes())
   else:
    throttle(url);raw=request(url);target.write_bytes(gzip.compress(raw));write_json(meta,{'sourceUrl':url,'checkedAt':datetime.now(timezone.utc).isoformat(),'sha256':digest(raw),'compression':'gzip'})
   tree=ET.fromstring(raw);nodes={int(n.attrib['id']):(float(n.attrib['lat']),float(n.attrib['lon'])) for n in tree.findall('node')}
   for item in tree:
    if item.tag not in ('node','way'):continue
    tags={t.attrib['k']:t.attrib['v'] for t in item.findall('tag')}
    if not tags.get('building') or not tags.get('addr:street') or not tags.get('addr:housenumber'):continue
    if item.tag=='node':point=nodes[int(item.attrib['id'])]
    else:
     points=[nodes[int(nd.attrib['ref'])] for nd in item.findall('nd') if int(nd.attrib['ref']) in nodes]
     if not points:continue
     point=((min(p[0] for p in points)+max(p[0] for p in points))/2,(min(p[1] for p in points)+max(p[1] for p in points))/2)
    row={'type':item.tag,'id':int(item.attrib['id']),'tags':tags,'center':{'lat':point[0],'lon':point[1]}}
    elements[(item.tag,row['id'])]=row
   print(city['city'],'map window',label,'candidates',len(elements),flush=True)
  except Exception as error:
   if split:
    west,south,east,north=bbox;midlon=(west+east)/2;midlat=(south+north)/2
    for i,box in enumerate([(west,south,midlon,midlat),(midlon,south,east,midlat),(west,midlat,midlon,north),(midlon,midlat,east,north)]):read_box(box,str(label)+'-'+str(i))
   else:
    errors.append({'window':label,'error':str(error)});print(city['city'],'map window',label,str(error),flush=True)
 for index,angle in enumerate([None,0,45,90,135,180,225,270,315]):
  lat,lon=center['latitude'],center['longitude']
  if angle is not None:
   lat+=radius*math.cos(math.radians(angle))/111.32
   lon+=radius*math.sin(math.radians(angle))/(111.32*math.cos(math.radians(lat)))
  read_box([lon-.014,lat-.011,lon+.014,lat+.011],index,split=True)
 if not elements:raise ValueError('bounded_map_unavailable: '+str(errors))
 return json.dumps({'elements':list(elements.values()),'method':'ordinary OSM public geographic windows','errors':errors},ensure_ascii=False).encode()

def build(args):
 out=pathlib.Path(args.output_directory);out.mkdir(parents=True,exist_ok=True);evidence=out/'evidence';evidence.mkdir(exist_ok=True)
 baseline=read_json(args.baseline);geography=read_json(pathlib.Path(__file__).resolve().parents[1]/'capital-geography.json');groups={}
 for case in baseline['cases']:groups.setdefault(case['regionId'],[]).append(case)
 archive=zipfile.ZipFile(args.candidate_archive) if args.candidate_archive else None
 previous=read_json(out/'candidates.json') if (out/'candidates.json').exists() else {'cities':[]}
 existing={c['regionId']:c for c in previous['cities']}
 envelope={'kind':'geographic-candidates','coverageInputsUsed':False,'cities':[]};problems=[]
 for region,cases in sorted(groups.items()):
  if args.regions and region not in args.regions.split(',') and region in existing:
   envelope['cities'].append(existing[region]);continue
  city={k:cases[0].get(k) for k in ['regionId','city','regionQuery','centerLatitude','centerLongitude','cityOsmRelation','community']};city['candidates']=[]
  if not city['cityOsmRelation']:city['cityOsmRelation']=next(c['osmRelation'] for c in geography['cities'] if c['regionId']==region)
  envelope['cities'].append(city);cache=evidence/(region+'-map.json')
  try:
   if not cache.exists():
    name=region.lower()+'-addresses.json'
    if archive and name in archive.namelist():raw=archive.read(name)
    elif args.bounded_map:raw=bounded_map(city,cases,evidence)
    else:
     try:raw=fetch_map(city)
     except Exception:raw=bounded_map(city,cases,evidence)
    cache.write_bytes(raw)
   data=json.loads(cache.read_bytes());rows={};old={(c['osmType'],c['osmId']) for c in cases}
   center={'latitude':city['centerLatitude'],'longitude':city['centerLongitude']}
   for element in data['elements']:
    tags=element.get('tags',{});point=element.get('center',element)
    if tags.get('building') not in ['house','apartments','residential','detached','semidetached_house','terrace'] or not tags.get('addr:street') or not tags.get('addr:housenumber') or (element['type'],element['id']) in old:continue
    if tags.get('addr:city') and tags['addr:city'].casefold()!=city['city'].casefold():continue
    if not isinstance(point.get('lat'),(int,float)) or not isinstance(point.get('lon'),(int,float)):continue
    row={'regionId':region,'city':city['city'],'latitude':point['lat'],'longitude':point['lon'],'osmType':element['type'],'osmId':element['id'],'exactStreet':tags['addr:street'],'exactHouse':tags['addr:housenumber'],'selectedWithoutQueueData':True}
    if distance_km(row,center)>40:continue
    identity=street_identity(row['exactStreet']);q=(row['latitude']>=city['centerLatitude'])*2+(row['longitude']>=city['centerLongitude'])
    distance=distance_km(row,center);zone='center' if distance<=2 else 'outer'
    key=(identity,zone,q)
    if key not in rows or digest(canonical(row))<digest(canonical(rows[key])):rows[key]=row
   # Queue-independent geographic ranking, bounded to200 candidates/city. Keep
   # different radii/quadrants and street identities before exact verification.
   ranked=sorted(rows.values(),key=lambda c:digest(canonical(c)))
   pools=[sorted([r for r in ranked if distance_km(r,center)<=2],key=lambda c:digest(canonical(c)))]
   for q in range(4):pools.append(sorted([r for r in ranked if distance_km(r,center)>2 and (r['latitude']>=city['centerLatitude'])*2+(r['longitude']>=city['centerLongitude'])==q],key=lambda c:distance_km(c,center),reverse=True))
   selected=[];seen=set()
   while len(selected)<200 and any(pools):
    for pool in pools:
     if pool:
      row=pool.pop(0);key=(row['osmType'],row['osmId'])
      if key not in seen:selected.append(row);seen.add(key)
   verified=[]
   for start in range(0,len(selected),50):
    batch=selected[start:start+50]
    url='https://nominatim.openstreetmap.org/lookup?'+urllib.parse.urlencode({'osm_ids':','.join(r['osmType'][0].upper()+str(r['osmId']) for r in batch),'format':'jsonv2','addressdetails':1,'accept-language':'uk'})
    name=f'{region}-lookup-'+digest(url.encode())[:16]+'.json';target=evidence/name;meta=evidence/(name+'.meta.json')
    if not target.exists() or not meta.exists():
     sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]));from request_budget import throttle
     throttle(url);raw=request(url);target.write_bytes(raw);write_json(meta,{'sourceUrl':url,'checkedAt':datetime.now(timezone.utc).isoformat(),'sha256':digest(raw)})
    metadata=read_json(meta);originals=read_json(target);indexed={(r.get('osm_type'),r.get('osm_id')):r for r in originals}
    for row in batch:
     original=indexed.get((row['osmType'],row['osmId']))
     if not original:continue
     row['verification']={'method':'nominatim-address','sourceUrl':metadata['sourceUrl'],'checkedAt':metadata['checkedAt'],'artifact':{'path':name,'sha256':metadata['sha256']}}
     verified.append(row)
   city['candidates']=verified;print(city['city'],len(verified),'verified candidate responses',flush=True)
  except Exception as e:problems.append({'city':city['city'],'error':str(e)});print(city['city'],str(e),flush=True)
  checkpoint={**envelope,'cities':sorted({**existing,**{c['regionId']:c for c in envelope['cities']}}.values(),key=lambda c:c['regionId'])}
  write_json(out/'candidates.json',checkpoint);write_json(out/'collection-report.json',{'problems':problems,'noQueueInputs':True})
 if archive:archive.close()
 result=generate(out/'candidates.json',args.baseline,evidence);write_json(out/'holdout.json',result)
 print(result['status'],len(result['cases']),'/440',flush=True)
 return result
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--baseline',default=str(pathlib.Path(__file__).with_name('baseline.json')));p.add_argument('--candidate-archive');p.add_argument('--output-directory',required=True);p.add_argument('--regions');p.add_argument('--bounded-map',action='store_true');a=p.parse_args();result=build(a);raise SystemExit(0 if result['status']=='frozen' else 1)
