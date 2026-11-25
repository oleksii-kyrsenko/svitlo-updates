"""Keep an observed published89 format failure distinct from live graph success."""
import datetime,hashlib,json,pathlib,re
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo
NEW_HEADER='Години відсутності електропостачання для всіх споживачів Черкаської області:'
def same_value(left,right):return json.dumps(left,sort_keys=True,ensure_ascii=False,allow_nan=False)==json.dumps(right,sort_keys=True,ensure_ascii=False,allow_nan=False)

def clock(value):
 if not isinstance(value,str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d|24:00',value):raise AssertionError('Invalid persisted interval clock')
 hour,minute=map(int,value.split(':'));return hour*60+minute

def identity(snapshot,original,expected):
 if snapshot.get('date')!=expected['date'] or snapshot.get('operatorId')!=original['operatorId'] or snapshot.get('queue')!=original['queue']:raise AssertionError('Wrong schedule date/operator/queue')

def live_snapshot(snapshot,original,expected):
 identity(snapshot,original,expected)
 if snapshot.get('status')!='ready' or snapshot.get('refreshError'):raise AssertionError('Current live schedule not ready')
 actual=[(clock(row['start']),clock(row['end'])) for row in snapshot.get('intervals',[])]
 if actual!=[tuple(row) for row in expected['queues'][original['queue']]]:raise AssertionError('Persisted intervals differ from independently observed official publication')
 if snapshot.get('sourceUrl') not in {v['sourceUrl'] for v in expected['versions']} or snapshot.get('provenance')!='official':raise AssertionError('Live official provenance differs')
 return snapshot

def current_format_proof(expected,directory,document_class,now=None):
 now=now or datetime.datetime.now(datetime.timezone.utc)
 if expected.get('date')!=now.astimezone(ZoneInfo('Europe/Kyiv')).date().isoformat():raise AssertionError('Format gate requires today original publication')
 observed=datetime.datetime.fromisoformat(expected['observedAt'].replace('Z','+00:00'))
 if observed.tzinfo is None or not -5<=(now-observed).total_seconds()<=600:raise AssertionError('Independent raw source observation is stale')
 proofs=[]
 for version in expected['versions']:
  order=version.get('order');url=urlsplit(version.get('sourceUrl',''))
  if isinstance(order,bool) or not isinstance(order,int) or not 0<=order<18 or url.scheme!='https' or url.netloc!='www.cherkasyoblenergo.com' or not url.path.startswith('/media/') or version.get('date')!=expected['date']:raise AssertionError('Invalid current official article identity')
  path=pathlib.Path(directory)/('article-'+str(order)+'.html');raw=path.read_bytes();digest=hashlib.sha256(raw).hexdigest()
  if digest!=version.get('sha256'):raise AssertionError('Original independently read article bytes changed')
  doc=document_class();doc.feed(raw.decode('utf-8'));doc.close()
  if doc.main_unbalanced or doc.main_frames or not doc.main_count or len(doc.main_blocks)!=1:raise AssertionError('Format gate requires a unique balanced innermost article body')
  lines=[re.sub(r'\s+:',':',' '.join(line.split())).casefold() for line in ''.join(doc.main_blocks[0]).splitlines()]
  if lines.count(NEW_HEADER.casefold())==1:proofs.append({'sourceUrl':version['sourceUrl'],'sha256':digest,'bytes':len(raw),'rawFile':path.name,'articleScope':'unique-balanced-leaf-main','globalMainCount':doc.main_count})
 if not proofs:raise AssertionError('Exact current regional header was not found inside the original article')
 return {'kind':'current-regional-source-format','verified':True,'date':expected['date'],'observedAt':expected['observedAt'],'header':NEW_HEADER,'articles':proofs}

def known_failure(snapshot,original,expected,visible,proof):
 identity(snapshot,original,expected)
 if snapshot.get('status')!='unsupported_format' or snapshot.get('refreshError') or any(snapshot.get(key) for key in ['intervals','slots','historySlots']):raise AssertionError('Baseline failure is not the observed empty unsupported-format result')
 if snapshot.get('sourceUrl')!='https://www.cherkasyoblenergo.com/off':raise AssertionError('Baseline failure belongs to another source')
 if not visible or visible.get('binding')!='visible-graph-failure-title-and-detail':raise AssertionError('The actual baseline graph failure is not visibly bound')
 if not proof or proof.get('verified') is not True or proof.get('kind')!='current-regional-source-format' or proof.get('date')!=expected['date'] or proof.get('header')!=NEW_HEADER or not proof.get('articles'):raise AssertionError('Current original source format was not independently verified')
 return {'kind':'observed-known-source-format-failure','liveSchedulePassed':False,'failureObserved':True,'snapshot':snapshot,'visibleFailure':visible,'independentRawFormatProof':proof}

def unchanged_upgrade(before,after,before_appearance,after_appearance):
 if not same_value(before,after) or not same_value(before_appearance,after_appearance):raise AssertionError('Install changed original saved state/cache/settings before launch')

def unchanged_settings(before,after):
 for key in ['notificationsEnabled','gpsAsked','endpoint','deleted','pushToken']:
  if not same_value(before.get(key),after.get(key)):raise AssertionError('Saved setting changed: '+key)

def unchanged_offline_snapshot(before,after):
 original={key:value for key,value in before.items() if key!='refreshError'}
 current={key:value for key,value in after.items() if key!='refreshError'}
 if not same_value(original,current):raise AssertionError('Offline restart changed the last successful official cache or its timestamp')
