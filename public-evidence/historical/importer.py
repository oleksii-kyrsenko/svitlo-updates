"""Pinned public exact-house snapshots, always historical and user-confirmed.

Fetching proves availability of an immutable publication, never current validity
of its queue assignments. Unsupported/ambiguous source scopes cannot become
positive records. This module never queries a subscriber or an operator form.
"""
import argparse,collections,datetime,hashlib,json,pathlib,re,subprocess,sys,time,unicodedata,urllib.request

ROOT=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
from manifest_io import serialize_manifest,write_manifest
DAY=86400000
MAX_SOURCE_AGE=180*DAY
MAX_FETCH_AGE=36*3600000
MAX_BYTES=2_000_000
MAX_RAW_BYTES=15_000_000
HOUSE=re.compile(r'\d{1,4}[а-яіїєґa-z]?(?:/\d{1,4}[а-яіїєґa-z]?)?',re.I)
QUEUE=re.compile(r'[1-6]\.[12]')
class SnapshotUnavailable(ValueError):
 def __init__(self,report):
  self.report=report
  super().__init__('No immutable snapshot successfully verified; previous manifest retained')

def compact(value):return json.dumps(value,ensure_ascii=False,separators=(',',':'))
def millis(value):
 if isinstance(value,bool):raise ValueError('Invalid date')
 if isinstance(value,int):return value
 date=datetime.datetime.fromisoformat(value.replace('Z','+00:00'))
 if date.tzinfo is None:raise ValueError('Publication timezone required')
 return int(date.timestamp()*1000)
def pointer(value):return str(value).replace('~','~0').replace('/','~1')
def house_key(value):return re.sub(r'\s+','',unicodedata.normalize('NFKC',value).lower()).replace('’',"'").replace('ʼ',"'")
def valid_house(value):return isinstance(value,str) and len(value)<=20 and HOUSE.fullmatch(unicodedata.normalize('NFKC',value)) is not None
def street_keys(values):
 result=subprocess.run(['node',str(ROOT/'normalize.mjs')],input=compact(values),text=True,capture_output=True,check=True,timeout=15)
 keys=json.loads(result.stdout)
 if len(keys)!=len(values):raise ValueError('Street identity count mismatch')
 return keys
def source_url(source):
 if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',source['repository']):raise ValueError('Invalid repository')
 if any(not re.fullmatch(r'[0-9a-f]{40}',source[k]) for k in ['commit','publishedCommit']):raise ValueError('Immutable Git commits required')
 path=source['path']
 if not re.fullmatch(r'[A-Za-z0-9_./-]+',path) or any(p in ('','..','.') for p in path.split('/')):raise ValueError('Invalid snapshot path')
 if not re.fullmatch(r'[0-9a-f]{64}',source['sha256']):raise ValueError('Raw SHA256 required')
 return 'https://raw.githubusercontent.com/'+source['repository']+'/'+source['commit']+'/'+path
def fetch(source):
 url=source_url(source)
 with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'SvitloHistoricalSnapshot/1.0'}),timeout=30) as response:
  if response.url!=url:raise ValueError('Unexpected snapshot redirect')
  raw=response.read(MAX_RAW_BYTES+1)
 if len(raw)>MAX_RAW_BYTES:raise ValueError('Snapshot size limit')
 return raw
def unique_object(pairs):
 result={}
 for key,value in pairs:
  if key in result:raise ValueError('Duplicate JSON object key')
  result[key]=value
 return result

def import_snapshot(raw,source,now):
 url=source_url(source);published=millis(source['publishedAt'])
 if not 0<=now-published<MAX_SOURCE_AGE:raise ValueError('Original publication outside 180-day historical window')
 if len(raw)>MAX_RAW_BYTES or hashlib.sha256(raw).hexdigest()!=source['sha256']:raise ValueError('Snapshot hash/size mismatch')
 if source.get('format')!='settlements-streets-gpv-v1':raise ValueError('Unsupported snapshot format')
 data=json.loads(raw,object_pairs_hook=unique_object)
 if data.get('meta',{}).get('region_code')!=source['regionId'] or data.get('meta',{}).get('dso_code')!=source['sourceDsoCode']:raise ValueError('Operator/region binding changed')
 if not re.fullmatch(r'UA\d{17}',source['katottg']):raise ValueError('KATOTTG required')
 matches=[(key,city) for key,city in data.get('settlements',{}).items() if city.get('katottg')==source['katottg']]
 if len(matches)!=1:raise ValueError('Ambiguous/missing source settlement')
 city_id,city=matches[0]
 if (city.get('name'),city.get('hromada'),city.get('type'))!=(source['settlement'],source['community'],'м.'):raise ValueError('Exact city geography changed')
 streets=city.get('streets')
 if not isinstance(streets,dict):raise ValueError('Missing GPV street map')
 labels=list(streets);identities=street_keys(labels);counts=collections.Counter(identities);stats=collections.Counter();records=[]
 context_pointer='/settlements/'+pointer(city_id)
 context={'verified':True,'settlement':city['name'],'community':city['hromada'],'regionId':source['regionId'],'quote':compact({k:city[k] for k in ['name','hromada','katottg']}),'jsonPointer':context_pointer,'basisUrl':url}
 for label,identity in zip(labels,identities):
  houses=streets[label]
  if not isinstance(houses,dict):stats['malformedStreets']+=1;continue
  stats['sourceHouses']+=len(houses)
  # Whole colliding street identities abstain, even when a source alias appears
  # harmless. Never choose a convenient representation of an ambiguous source.
  if not identity or counts[identity]!=1:stats['streetCollisionHouses']+=len(houses);continue
  if not isinstance(label,str) or not 1<=len(label)<=180 or re.search(r'[,;\n\r]|непарн|частков|крім|окрім',label,re.I):stats['qualifiedStreetHouses']+=len(houses);continue
  unknown={house_key(h) for h,q in houses.items() if not isinstance(q,list) or len(q)!=1 or not isinstance(q[0],str) or not QUEUE.fullmatch(q[0]) or not valid_house(h)}
  # A literal compound selector could overlap another listed house. Do not
  # split it or guess a boundary; conservatively withdraw the entire street.
  malformed=[h for h in houses if not valid_house(h)]
  if malformed:stats['unsupportedSelectors']+=len(malformed);stats['unsupportedStreetHouses']+=len(houses);continue
  grouped=collections.defaultdict(list);by_identity=collections.defaultdict(list)
  for h,q in houses.items():by_identity[house_key(h)].append(q)
  conflicts={key for key,values in by_identity.items() if len({compact(v) for v in values})!=1}
  blocked=unknown|conflicts
  seen_houses=set()
  for h,q in houses.items():
   if house_key(h) in blocked:
    stats['vetoedHouses']+=1;continue
   if house_key(h) in seen_houses:stats['duplicateEquivalentHouses']+=1;continue
   seen_houses.add(house_key(h))
   grouped[q[0]].append(h)
  for queue,keys in grouped.items():
   chunks=[];chunk=[]
   for h in keys:
    candidate=chunk+[h];quote=compact({label:{k:houses[k] for k in candidate}})
    if chunk and (len(candidate)>100 or len(quote.encode())>2500):chunks.append(chunk);chunk=[h]
    else:chunk=candidate
   if chunk:chunks.append(chunk)
   for chunk in chunks:
    quote=compact({label:{h:houses[h] for h in chunk}})
    if len(quote.encode())>2500:raise ValueError('Single-house quote exceeds budget')
    snapshot={k:source[k] for k in ['repository','commit','path','sha256','publishedCommit']}
    snapshot.update(publishedAt=published,jsonPointer=context_pointer+'/streets/'+pointer(label))
    record={'recordVersion':5,'evidenceType':'historical-directory','historical':True,'requiresConfirmation':True,'method':'direct','operatorId':source['operatorId'],'regionId':source['regionId'],'community':city['hromada'],'settlement':city['name'],'katottg':city['katottg'],'street':label,'scope':'house','queue':queue,'houses':chunk,'quote':quote,'sourceUrl':url,'sourceSnapshot':snapshot,'sourceContext':context,'publishedAt':published,'fetchedAt':now,'expiresAt':min(now+7*DAY,published+MAX_SOURCE_AGE)}
    record['id']=hashlib.sha256(compact({k:v for k,v in record.items() if k not in ['fetchedAt','expiresAt']}).encode()).hexdigest()[:32]
    records.append(record)
 stats['records']=len(records);stats['acceptedHouses']=sum(len(r['houses']) for r in records)
 return records,dict(stats)

def source_family(value):
 snapshot=value.get('sourceSnapshot',value)
 keys=[value.get(k) for k in ['operatorId','regionId','katottg']]+[snapshot.get(k) for k in ['repository','path']]
 return tuple(keys) if all(isinstance(x,str) and x for x in keys) else None

def merge_records(manifest,accepted,read_urls,now,read_families=None):
 if manifest.get('schemaVersion')!=2 or not isinstance(manifest.get('records'),list):raise ValueError('Unsupported manifest')
 families={source_family(r) for r in accepted} if read_families is None else read_families
 families.discard(None)
 previous=[r for r in manifest['records'] if not (r.get('evidenceType')=='historical-directory' and (r.get('sourceUrl') in read_urls or source_family(r) in families))]
 records=list({r['id']:r for r in previous+accepted}.values())
 if len(records)>10000:raise ValueError('Complete manifest record budget exceeded')
 result={**manifest,'generatedAt':now,'records':records}
 serialize_manifest(result)
 return result

def collect(config,manifest,now,reader=fetch):
 if config.get('schemaVersion')!=1:raise ValueError('Unsupported configuration')
 if not isinstance(config.get('enabled'),bool) or not isinstance(config.get('sources'),list):raise ValueError('Invalid historical reader controls')
 families=[source_family(source) for source in config['sources']] if config['enabled'] else []
 if None in families or len(families)!=len(set(families)):raise ValueError('Historical source families must be unique')
 accepted=[];read_urls=set();read_families=set();report={'startedAt':now,'sources':[],'errors':[]}
 for source in (config.get('sources',[]) if config.get('enabled') else []):
  try:
   raw=reader(source);records,stats=import_snapshot(raw,source,now);accepted.extend(records);read_urls.add(source_url(source));read_families.add(source_family(source));report['sources'].append({'id':source['id'],'url':source_url(source),'sha256':source['sha256'],'publishedAt':millis(source['publishedAt']),**stats})
  except Exception as exc:report['errors'].append({'id':source.get('id'),'error':str(exc)[:250]})
 if not config.get('enabled'):accepted=[];read_urls={r.get('sourceUrl') for r in manifest['records'] if r.get('evidenceType')=='historical-directory'}
 if config.get('enabled') and not read_urls:raise SnapshotUnavailable({**report,'status':'source-unavailable','manifestChanged':False})
 result=merge_records(manifest,accepted,read_urls,now,read_families)
 report.update(finishedAt=now,records=len(accepted),totalRuntimeRecords=len(result['records']),serializedBytes=len(serialize_manifest(result).encode()),mode='historical-user-confirmation')
 return result,report

def monitor_revision(source,raw):
 """Report changed upstream bytes for review; never renew publication dates."""
 url='https://api.github.com/repos/'+source['repository']+'/contents/'+source['path']
 with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'SvitloHistoricalSnapshot/1.0','Accept':'application/vnd.github+json'}),timeout=20) as response:
  body=response.read(100_001)
 if len(body)>100_000:raise ValueError('Revision metadata size limit')
 metadata=json.loads(body);current=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
 if not re.fullmatch(r'[0-9a-f]{40}',metadata.get('sha','')):raise ValueError('Missing upstream blob identity')
 return {'url':url,'pinnedBlobSha1':current,'upstreamBlobSha1':metadata['sha'],'changed':current!=metadata['sha'],'action':'review-new-pin-and-original-publication' if current!=metadata['sha'] else 'unchanged-publication'}

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--config',type=pathlib.Path,default=ROOT/'sources.json');parser.add_argument('--manifest',type=pathlib.Path,default=ROOT.parent/'manifest.json');parser.add_argument('--output',type=pathlib.Path);parser.add_argument('--report',type=pathlib.Path,default=ROOT.parent/'historical-report.json');parser.add_argument('--proof-dir',type=pathlib.Path);parser.add_argument('--monitor',action='store_true');args=parser.parse_args()
 now=int(time.time()*1000);config=json.loads(args.config.read_text());proofs={}
 def read(source):
  raw=fetch(source);proofs[source['id']]=(source,raw);return raw
 try:result,report=collect(config,json.loads(args.manifest.read_text()),now,read)
 except SnapshotUnavailable as exc:
  args.report.write_text(json.dumps(exc.report,ensure_ascii=False,indent=2)+'\n');raise
 if args.proof_dir:
  args.proof_dir.mkdir(parents=True,exist_ok=True)
  for index,(source,raw) in enumerate(proofs.values()):
   (args.proof_dir/(str(index)+'.json')).write_bytes(raw)
   (args.proof_dir/(str(index)+'.provenance.json')).write_text(compact({'source':source,'readAt':now,'observedSha256':hashlib.sha256(raw).hexdigest()}))
 if args.monitor:
  for item in report['sources']:
   source,raw=proofs[item['id']]
   try:item['revisionMonitor']=monitor_revision(source,raw)
   except Exception as exc:item['revisionMonitor']={'error':str(exc)[:200],'action':'retain-reviewed-pin'}
 target=args.output or args.manifest;write_manifest(target,result)
 args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(compact(report))
if __name__=='__main__':main()
