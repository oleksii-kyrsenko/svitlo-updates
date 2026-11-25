"""External live-schedule regression, not address/queue coverage.

One pre-existing external fixture supplies the already-known queue, matching the
reported failure. No schedule or interval is seeded. All expected intervals are
read from the real official publication independently in source.py.
"""
import copy,datetime,hashlib,importlib.util,json,pathlib,re,sqlite3,subprocess,time,traceback,xml.etree.ElementTree as E
ROOT=pathlib.Path('.github/qa');spec=importlib.util.spec_from_file_location('screen_evidence',ROOT/'native90/popivka/screen.py');screen=importlib.util.module_from_spec(spec);spec.loader.exec_module(screen);c=screen.load_helpers(ROOT/'native90/apk-smoke.py')
spec=importlib.util.spec_from_file_location('capture_reader',ROOT/'audit-result-evidence.py');capture_reader=importlib.util.module_from_spec(spec);spec.loader.exec_module(capture_reader)
adb,xml,launch,evidence,out,pkg=(c[k] for k in ['adb','xml','launch','evidence','out','pkg'])
spec=importlib.util.spec_from_file_location('native_contract',ROOT/'native90/contract.py');contract=importlib.util.module_from_spec(spec);spec.loader.exec_module(contract)
spec=importlib.util.spec_from_file_location('official_observation',ROOT/'native90/popivka/source.py');source=importlib.util.module_from_spec(spec);spec.loader.exec_module(source)
spec=importlib.util.spec_from_file_location('baseline_gate',ROOT/'native90/popivka/baseline-gate.py');baseline_gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(baseline_gate)
meta=json.loads((ROOT/'native90/meta.json').read_text());baseline=json.loads((ROOT/'native90/baseline-89.json').read_text());flags={};result={'scope':'External saved-correct-queue fixture; LIVE official schedule regression only. No address/queue lookup or coverage success is claimed.','candidate':meta,'api':adb('shell','getprop','ro.build.version.sdk').strip()}

def dump_state(label):
 for attempt in range(3):
  directory=out/'database'/label/('capture-'+str(attempt+1));directory.mkdir(parents=True,exist_ok=False)
  adb('pull',f'/data/data/{pkg}/databases',str(directory))
  files=[{'path':str(p.relative_to(directory)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(directory.rglob('*')) if p.is_file()]
  record={'capturedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'readOnly':True,'files':files};proof=directory/'capture.json';proof.write_text(json.dumps(record,indent=2)+'\n')
  database=next(directory.rglob('RKStorage'))
  try:
   with capture_reader.read_only_capture(database) as db:
    integrity=db.execute('PRAGMA integrity_check').fetchone()[0]
    if integrity!='ok':raise AssertionError('Retained SQLite integrity check failed: '+integrity)
    row=db.execute('SELECT value FROM catalystLocalStorage WHERE key=?',('svitlo.state.v1',)).fetchone()
    appearance=db.execute('SELECT value FROM catalystLocalStorage WHERE key=?',('svitlo.appearance.v1',)).fetchone()
  except sqlite3.DatabaseError as error:
   record['sqliteError']=str(error);record['retry']=str(error) in ['attempt to write a readonly database','database disk image is malformed'] and attempt<2;proof.write_text(json.dumps(record,indent=2)+'\n')
   if not record['retry']:raise
   time.sleep(.25);continue
  record['integrity']=integrity;record['readCompleted']=True;proof.write_text(json.dumps(record,indent=2)+'\n')
  if not row:raise AssertionError('Application state missing')
  if not appearance:raise AssertionError('Saved appearance state missing')
  (out/(label+'-appearance.json')).write_text(json.dumps(json.loads(appearance[0]),ensure_ascii=False,indent=2)+'\n')
  state=json.loads(row[0]);(out/(label+'-state.json')).write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n');return state

def seed_external_fixture():
 state=json.loads((ROOT/'native90/fixture.json').read_text());place=state['places'][0]
 place.update(queueOrigin='manual',queueConfirmed=True,queueCheckedAt=int(time.time()*1000),name='Дім')
 state.update(activePlaceId=place['id'],notificationsEnabled=False,snapshots={},gpsAsked=True)
 adb('shell','am','force-stop',pkg);database=out/'external-fixture-RKStorage'
 with sqlite3.connect(database) as db:
  db.execute('CREATE TABLE catalystLocalStorage(key TEXT PRIMARY KEY,value TEXT NOT NULL)');db.execute('PRAGMA user_version=1')
  for key,value in [('svitlo.state.v1',state),('svitlo.appearance.v1',{'version':1,'theme':'aurora'})]:db.execute('INSERT INTO catalystLocalStorage VALUES (?,?)',(key,json.dumps(value,ensure_ascii=False)))
 remote=f'/data/data/{pkg}/databases';adb('shell','mkdir','-p',remote);adb('push',str(database),remote+'/RKStorage');uid=adb('shell','stat','-c','%u',f'/data/data/{pkg}').strip();assert uid.isdigit();adb('shell','chown','-R',uid+':'+uid,remote);adb('shell','restorecon','-R',remote)
 (out/'external-fixture.json').write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n');return copy.deepcopy(place)

def same_place(state,original):
 assert state.get('activePlaceId')==original['id'],'Active address changed'
 matches=[p for p in state.get('places',[]) if p['id']==original['id']];assert len(matches)==1
 for key in ['id','address','name','operatorId','queue','queueOrigin','queueConfirmed','reminders']:
  assert baseline_gate.same_value(matches[0].get(key),original.get(key)),(key,matches[0].get(key),original.get(key))
 return matches[0]

def expected_snapshot(state,original,expected):
 same_place(state,original);snapshot=state.get('snapshots',{}).get(original['id'],{}).get('today',{})
 return baseline_gate.live_snapshot(snapshot,original,expected)

def wait_baseline(original,expected):
 deadline=time.monotonic()+150;attempt=0
 while time.monotonic()<deadline:
  attempt+=1;s=xml()
  if 'current-address-card' in s and 'schedule-graph' in s:
   state=dump_state('baseline89-observed-'+str(attempt));same_place(state,original)
   snapshot=state.get('snapshots',{}).get(original['id'],{}).get('today',{})
   if snapshot.get('status')=='ready':
    expected_snapshot(state,original,expected);visible_graph('baseline89-live-graph',expected)
    return {'kind':'live-schedule-matches','liveSchedulePassed':True,'failureObserved':False,'snapshot':snapshot}
   if snapshot.get('status')=='unsupported_format':
    proof=baseline_gate.current_format_proof(expected,out/'source-before-baseline',source.Document)
    c['top']()
    for page in range(8):
     current=xml();binding=screen.graph_failure_evidence(current)
     if binding:
      outcome=baseline_gate.known_failure(snapshot,original,expected,binding,proof);evidence('baseline89-observed-format-failure',current)
      (out/'baseline89-observed-format-failure.json').write_text(json.dumps(outcome,ensure_ascii=False,indent=2)+'\n');return outcome
     c['scroll_down'](E.fromstring(current))
    raise AssertionError('Baseline unsupported-format status did not have the actual visible graph failure')
   if snapshot.get('status') not in [None,'loading']:raise AssertionError('Unexpected baseline schedule status: '+str(snapshot.get('status')))
  time.sleep(7)
 raise AssertionError('Baseline did not show a verified live graph or the specific observed current-format failure')

def wait_snapshot(original,expected,label):
 deadline=time.monotonic()+150;attempt=0;last_error=None
 while time.monotonic()<deadline:
  attempt+=1;s=xml()
  if 'current-address-card' in s and 'schedule-graph' in s:
   state=dump_state(label+'-'+str(attempt))
   try:return state,expected_snapshot(state,original,expected)
   except AssertionError as error:last_error=str(error)
  time.sleep(7)
 raise AssertionError('Live schedule did not match official source within150s: '+str(last_error))

def visible_graph(label,expected):
 c['top']();c['wait_for']('current-address-card','schedule-graph')
 for attempt in range(8):
  s=xml();heading=screen.graph_evidence(s)
  if heading:break
  c['scroll_down'](E.fromstring(s))
 else:raise AssertionError('Daily graph heading is not visible')
 evidence(label+'-heading',s)
 now=datetime.datetime.now(source.zoneinfo.ZoneInfo('Europe/Kyiv'));minute=now.hour*60+now.minute
 ranges=expected['queues']['3.1'];target=next((r for r in ranges if r[1]>minute),ranges[-1])
 for attempt in range(12):
  s=xml();binding=screen.graph_evidence(s,target)
  if binding:break
  c['scroll_down'](E.fromstring(s))
 else:raise AssertionError('Expected actual interval range is not visible in the graph: '+str(target))
 assert 'android:id/alertTitle' not in s and 'app-message-dialog' not in s
 evidence(label,s);(out/(label+'-visible-binding.json')).write_text(json.dumps(binding,ensure_ascii=False,indent=2)+'\n');return s

try:
 adb('logcat','-c');adb('shell','wm','size','1080x2340');adb('shell','wm','density','440');adb('shell','settings','put','system','font_scale','1.0');adb('shell','svc','wifi','enable');adb('shell','svc','data','enable')
 expected=source.observe(out/'source-before-baseline');result['officialBeforeBaseline']=expected
 adb('install','-r','-g','--abi','x86_64','previous.apk');contract.verify_installed(adb,baseline,out/'baseline-installed.json');original=seed_external_fixture();launch();baseline_outcome=wait_baseline(original,expected)
 result['baselineObservedOutcome']=baseline_outcome;result['baselineSnapshot']=baseline_outcome['snapshot'];flags['Baseline89AddressAndQueueRetained']=True
 # A real baseline format failure stays an observed FAILURE, not a graph pass.
 flags['Baseline89OutcomeExplicitlyVerified']=True
 adb('shell','am','force-stop',pkg);before=dump_state('baseline-stopped-before-upgrade');same_place(before,original);before_appearance=json.loads((out/'baseline-stopped-before-upgrade-appearance.json').read_text())
 adb('install','-r','-g','--abi','x86_64','candidate/'+meta['fileName']);contract.verify_installed(adb,meta,out/'candidate-installed.json');after_install=dump_state('after-install-before-launch');same_place(after_install,original);after_appearance=json.loads((out/'after-install-before-launch-appearance.json').read_text());baseline_gate.unchanged_upgrade(before,after_install,before_appearance,after_appearance);flags['UpgradeKeepsExactOriginalStateCacheSettingsAndAppearance']=True
 expected=source.observe(out/'source-before-candidate');result['officialBeforeCandidate']=expected;launch();state,snapshot=wait_snapshot(original,expected,'candidate-live');baseline_gate.unchanged_settings(before,state);visible_graph('candidate90-live-graph',expected);result['candidateSnapshot']=snapshot;flags['CandidateRealOfficialTodayIntervalsMatch']=True
 # Capture the queue/source card in its own screenshot; a long graph may place it below the viewport.
 c['wait_source']('Черга '+original['queue'],original['address']);evidence('candidate90-source-address',xml());flags['ExactAddressAndQueueVisible']=True
 contract.block_app_network(adb,out/'offline-isolation.json');adb('shell','am','force-stop',pkg)
 # While graph/source screenshots were taken, a legitimate online refresh may
 # have committed a newer checkedAt. Anchor the last persisted successful cache
 # AFTER network isolation and force-stop, before the offline restart.
 frozen=dump_state('network-blocked-before-restart');snapshot=expected_snapshot(frozen,original,expected)
 assert baseline_gate.same_value(json.loads((out/'network-blocked-before-restart-appearance.json').read_text()),before_appearance),'Saved appearance changed after launch'
 baseline_gate.unchanged_settings(before,frozen)
 result['lastSuccessfulSnapshotBeforeOfflineRestart']=snapshot
 launch();c['wait_for']('current-address-card','schedule-graph');time.sleep(5);visible_graph('candidate90-offline-restart',expected);offline=dump_state('offline-restart');same_place(offline,original)
 cached=offline.get('snapshots',{}).get(original['id'],{}).get('today',{});baseline_gate.unchanged_offline_snapshot(snapshot,cached);baseline_gate.unchanged_settings(before,offline);assert baseline_gate.same_value(json.loads((out/'offline-restart-appearance.json').read_text()),before_appearance),'Offline restart changed saved appearance';flags['OfflineRestartKeepsExactOfficialCacheAndSourceTimestamp']=True
except Exception as error:
 result.update(error=str(error),traceback=traceback.format_exc());raise
finally:
 result.update(flags=flags,allPassed=len(flags)==6 and all(flags.values()))
 try:
  (out/'final-logcat.txt').write_text(adb('logcat','-d',check=False));(out/'final-screen.png').write_bytes(subprocess.check_output(['adb','exec-out','screencap','-p'],timeout=60));(out/'final-screen.xml').write_text(xml())
 except Exception as error:result['diagnosticError']=str(error)[:300]
 (out/'popivka-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print('POPIVKA_RESULT',json.dumps(result,ensure_ascii=False),flush=True)
assert result['allPassed'],'Live Popivka schedule acceptance incomplete'
