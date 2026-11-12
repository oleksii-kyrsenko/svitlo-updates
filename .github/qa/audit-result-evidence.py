"""Separate user-assisted street choices and bind app projections to one attempt.

The projection is app-written public evidence. Its hash identifies this exported
JSON value; it does not authenticate an original HTTP response or its truth.
"""
import collections,contextlib,hashlib,json,pathlib,re,shutil,sqlite3,tempfile

MAX_PROJECTION_BYTES=196608
SUPPORTED={'dtek-kyiv','dtek-dnipro','cek','cherkasy'}

def encoded(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')
def sha(raw):return hashlib.sha256(raw).hexdigest()
@contextlib.contextmanager
def read_only_capture(database):
 # SQLite's read-only WAL reader can update its local shared-memory sidecar.
 # Analyze a whole-directory copy so every original captured byte survives.
 database=pathlib.Path(database).resolve()
 with tempfile.TemporaryDirectory(prefix='svitlo-capture-analysis-') as temporary:
  analysis=pathlib.Path(temporary)/'database';shutil.copytree(database.parent,analysis)
  with sqlite3.connect('file:'+str(analysis/database.name)+'?mode=ro',uri=True) as connection:yield connection
def user_selected(result,place):
 return result.get('streetResolution')=='user_selected' or result.get('queueStreetResolution')=='user_selected' or place.get('queueStreetResolution')=='user_selected'

def confirmed_outcome(result,place):
 if not(place.get('queueConfirmed') is True and place.get('queue')):raise ValueError('A confirmed queue is required')
 if result.get('visibleQueue')!=place['queue']:raise ValueError('Visible and saved queues differ')
 if place.get('queueOrigin')=='public':return 'queue_found_public'
 if place.get('queueOrigin')!='official':raise ValueError('Confirmed audit queues require official or public provenance')
 return 'confirmed_source_street' if user_selected(result,place) else 'queue_found_official'

def automatic_contribution(result):
 place=result.get('persistedPlace') or {}
 return int(result.get('outcome')=='queue_found_official' and place.get('queueOrigin')=='official' and place.get('queueConfirmed') is True and bool(place.get('queue')) and result.get('visibleQueue')==place['queue'] and not user_selected(result,place) and place.get('queueStreetResolution') in [None,'automatic'] and result.get('streetResolution') in [None,'automatic'] and not result.get('queueEnteredManually') and not result.get('addressStorageSeeded'))

def summary(results):
 return {'denominator':len(results),'observedUIOfficialAutomatic':sum(automatic_contribution(r) for r in results),
         'observedUIConfirmedSourceStreet':sum(r.get('outcome')=='confirmed_source_street' for r in results),
         'independentlyQualifiedCorrect':None,'independentQualificationStatus':'pending',
         'outcomes':dict(sorted(collections.Counter(r.get('outcome','missing') for r in results).items())),
         'definition':'App-confirmed official queue with visible saved address; explicit source-street choices are separate. Source projections still require independent review.'}

def contained(root,name):
 path=(root/name).resolve()
 if not path.is_relative_to(root.resolve()) or path==root.resolve():raise ValueError('Attempt evidence path escapes its case directory')
 return path

def capture_reference(case_dir,capture):
 if not isinstance(capture,dict) or not isinstance(capture.get('path'),str):raise ValueError('Read-only app-state capture reference is missing')
 path=contained(case_dir,capture['path']);raw=path.read_bytes()
 if sha(raw)!=capture.get('sha256'):raise ValueError('Read-only capture metadata changed')
 metadata=json.loads(raw)
 if metadata.get('readOnly') is not True or metadata.get('readCompleted') is not True:raise ValueError('App-state capture was not a completed read-only observation')
 files=[]
 for item in metadata.get('files',[]):
  target=contained(path.parent,item['path']);original=target.read_bytes()
  if sha(original)!=item['sha256'] or len(original)!=item.get('size',item.get('bytes')):raise ValueError('Original app-state capture bytes changed')
  files.append({'path':str(target.relative_to(case_dir.resolve())),'bytes':len(original),'sha256':sha(original)})
 if not any(pathlib.Path(item['path']).name=='RKStorage' for item in files):raise ValueError('App-state SQLite capture is missing')
 return {**capture,'files':files}

def verify_captured_state(case_dir,reference,state):
 databases=[item for item in reference['files'] if pathlib.Path(item['path']).name=='RKStorage']
 if len(databases)!=1:raise ValueError('Expected one exact app-state SQLite capture')
 database=contained(case_dir,databases[0]['path'])
 with read_only_capture(database) as connection:
  row=connection.execute('SELECT value FROM catalystLocalStorage WHERE key=?',('svitlo.state.v1',)).fetchone()
 if not row or encoded(json.loads(row[0]))!=encoded(state):raise ValueError('Attempt state differs from its original SQLite capture')

def result_binding(evidence,place):
 binding=evidence.get('resultBinding')
 if not isinstance(binding,dict) or binding.get('operatorId')!=(place.get('operatorId') if place.get('operatorId') in SUPPORTED else None) or binding.get('status')!=place.get('queueCheckStatus'):raise ValueError('Public projection final reader/status does not match saved lookup')
 if binding['status']=='ready' and binding.get('queue')!=place.get('queue'):raise ValueError('Public projection queue differs from the final saved result')
 provider=binding.get('provider')
 if provider not in [None,'yasno','cherkasy']:raise ValueError('Public projection has an unsupported final reader')
 if evidence.get('unsupportedResult') is not (provider is None):raise ValueError('Public projection final-reader support flag differs')
 if provider is None and evidence.get('complete') is True:raise ValueError('Unsupported final reader cannot have complete projection evidence')
 # Only ready results persist queueAdapter/queueSource/transport as final queue
 # provenance. A failed current check can leave earlier queue provenance saved.
 if provider is not None and binding['status']=='ready':
  if place.get('queueTransport') not in [None,'native'] or place.get('queueEvidence') or place.get('queueCacheFetchedAt') or place.get('queueCacheExpiresAt'):raise ValueError('A cached/document/fallback result cannot use another reader projection')
  if provider=='yasno' and not(place.get('operatorId') in ['dtek-kyiv','dtek-dnipro','cek'] and place.get('queueAdapter')=='yasno'):raise ValueError('YASNO projection does not belong to the final adapter')
  if provider=='cherkasy' and not(place.get('operatorId')=='cherkasy' and place.get('queueSource')=='https://www.cherkasyoblenergo.com/off'):raise ValueError('Cherkasy projection does not belong to the final source')
 return binding

def persist_projection(case,result,state,capture,case_dir):
 case_dir=pathlib.Path(case_dir).resolve();place=result.get('persistedPlace') or {}
 if result.get('id')!=case['id'] or not re.fullmatch(r'[a-f0-9]{64}',result.get('apkSha256','')):raise ValueError('Attempt case or installed APK identity is missing')
 if not place.get('id') or state.get('activePlaceId')!=place['id'] or [p for p in state.get('places',[]) if p.get('id')==place['id']]!=[place]:raise ValueError('Evidence does not belong to the saved active address')
 reference=capture_reference(case_dir,capture)
 verify_captured_state(case_dir,reference,state)
 evidence=place.get('queueCheckSourceEvidence')
 if evidence is None:return {'status':'missing','expectedForOperator':place.get('operatorId') in SUPPORTED,'independentQualificationStatus':'pending','readOnlyStateCapture':reference}
 raw=encoded(evidence)
 if len(raw)>MAX_PROJECTION_BYTES or not isinstance(evidence,dict) or evidence.get('schemaVersion')!=1 or evidence.get('kind')!='public-source-evidence' or evidence.get('evidenceLevel')!='sanitized-public-projection' or not isinstance(evidence.get('entries'),list):raise ValueError('App projection is unbounded or has an unsupported schema')
 binding=result_binding(evidence,place)
 target=case_dir/'public-source-projection.json';target.write_bytes(raw)
 return {'status':'captured','path':target.name,'sha256':sha(raw),'bytes':len(raw),
         'evidenceLevel':'sanitized-public-projection','independentlyVerified':False,
         'independentQualificationStatus':'pending',
         'captureComplete':evidence.get('complete') is True,'truncated':evidence.get('truncated'),
         'resultBinding':binding,'unsupportedResult':evidence.get('unsupportedResult'),
         'droppedEvents':evidence.get('droppedEvents'),'unsupportedOperator':evidence.get('unsupportedOperator'),
         'readOnlyStateCapture':reference,'placeId':place['id'],
         'placeValueSha256':sha(encoded(place)),'stateValueSha256':sha(encoded(state)),
         'scheduleSnapshotValueSha256':sha(encoded(state.get('snapshots',{}).get(place['id']))),
         'interpretation':'Hash of exported app-written public JSON projection value; not original HTTP bytes or independent source verification.'}

def bind_attempt(case,result,case_dir):
 case_dir=pathlib.Path(case_dir).resolve();path=case_dir/'result.json'
 if json.loads(path.read_bytes())!=result or result.get('id')!=case['id']:raise ValueError('Saved original result differs from this attempt')
 artifact=result.get('sourceEvidenceArtifact')
 if artifact:
  capture_reference(case_dir,artifact['readOnlyStateCapture'])
  if artifact.get('status')=='captured':
   raw=contained(case_dir,artifact['path']).read_bytes()
   if sha(raw)!=artifact['sha256'] or len(raw)!=artifact['bytes'] or encoded(json.loads(raw))!=encoded((result.get('persistedPlace') or {}).get('queueCheckSourceEvidence')):raise ValueError('Exported projection changed before binding the original attempt')
 files=[]
 for target in sorted(case_dir.iterdir()):
  if target.is_file() and (target.name in ['result.json','public-source-projection.json'] or target.suffix in ['.png','.xml']):
   raw=target.read_bytes();files.append({'path':target.name,'bytes':len(raw),'sha256':sha(raw)})
 binding={'schemaVersion':1,'kind':'one-Android-attempt-evidence-binding','caseId':case['id'],
          'apkSha256':result.get('apkSha256'),'androidApi':result.get('androidApi'),
          'sampleSha256':result.get('sampleSha256'),'auditCommit':result.get('auditCommit'),
          'placeId':(result.get('persistedPlace') or {}).get('id'),
          'target':{k:case.get(k) for k in ['city','regionId','exactStreet','exactHouse']},
          'sourceEvidenceArtifact':artifact,'files':files,
          'interpretation':'Binds the retained original result/screens/state capture and sanitized app projection to the same attempt; source truth requires independent review.'}
 (case_dir/'attempt-evidence-binding.json').write_bytes(encoded(binding))
 return binding
