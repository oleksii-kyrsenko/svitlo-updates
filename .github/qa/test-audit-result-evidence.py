"""Controls against assisted-result inflation and evidence from another attempt."""
import copy,hashlib,importlib.util,json,pathlib,shutil,sqlite3,tempfile,unittest
s=importlib.util.spec_from_file_location('evidence',pathlib.Path(__file__).with_name('audit-result-evidence.py'));e=importlib.util.module_from_spec(s);s.loader.exec_module(e)

def fixture(root):
 projection={'schemaVersion':1,'kind':'public-source-evidence','evidenceLevel':'sanitized-public-projection','operatorId':'cherkasy','entries':[{'operatorId':'cherkasy','provider':'cherkasy','stage':'house-gpv','observedAt':1794400000000,'sourceObservedAt':1794390000000,'fromDictionaryCache':True,'rows':[{'house':'12','gpvRaw':'4.2','unknown':False},{'house':'12','gpvRaw':'unreadable','unknown':True}],'counts':{'discovered':2,'requested':2,'completed':2,'unknown':1},'complete':True,'redacted':False,'truncated':False}],'resultBinding':{'provider':'cherkasy','operatorId':'cherkasy','status':'ready','queue':'4.2'},'unsupportedResult':False,'complete':True,'truncated':False,'droppedEvents':0,'unsupportedOperator':False}
 place={'id':'app-written-address','operatorId':'cherkasy','address':'Зразок, вулиця Нова, 12','addressParts':{'settlement':'Зразок','street':'вулиця Нова','house':'12'},'queueConfirmed':True,'queueOrigin':'official','queue':'4.2','queueStreetResolution':'automatic','queueStreetSelectedAt':None,'queueCheckStatus':'ready','queueSource':'https://www.cherkasyoblenergo.com/off','queueTransport':'native','queueCheckSourceEvidence':projection}
 state={'activePlaceId':place['id'],'places':[place],'snapshots':{place['id']:{'today':{'queue':'4.2','checkedAt':'original'}}}}
 case={'id':'frozen-case','city':'Зразок','regionId':'UA-71','exactStreet':'вулиця Нова','exactHouse':'12'}
 result={'id':case['id'],'apkSha256':'a'*64,'sampleSha256':'b'*64,'androidApi':35,'auditCommit':'c'*40,'persistedPlace':place,'visibleQueue':'4.2','outcome':'queue_found_official','queueEnteredManually':False,'addressStorageSeeded':False}
 capture=write_capture(root,state)
 return case,result,state,place,capture

def write_capture(root,state):
 directory=root/'database/capture-001';directory.mkdir(parents=True,exist_ok=True);db=directory/'RKStorage'
 db.unlink(missing_ok=True)
 with sqlite3.connect(db) as connection:
  connection.execute('CREATE TABLE catalystLocalStorage(key TEXT PRIMARY KEY,value TEXT)');connection.execute('INSERT INTO catalystLocalStorage VALUES (?,?)',('svitlo.state.v1',json.dumps(state,ensure_ascii=False)))
 metadata={'readOnly':True,'readCompleted':True,'files':[{'path':db.name,'size':db.stat().st_size,'sha256':e.sha(db.read_bytes())}]};path=directory/'capture.json';path.write_bytes(e.encoded(metadata))
 return {'path':str(path.relative_to(root)),'sha256':e.sha(path.read_bytes())}

class ResultEvidence(unittest.TestCase):
 def test_user_selected_results_cannot_enter_automatic_official_numerator(self):
  with tempfile.TemporaryDirectory() as folder:
   _,result,_,place,_=fixture(pathlib.Path(folder));self.assertEqual(e.confirmed_outcome(result,place),'queue_found_official');self.assertEqual(e.automatic_contribution(result),1)
   for location in ['streetResolution','queueStreetResolution','persistedPlace']:
    attempt=copy.deepcopy(result)
    if location=='persistedPlace':attempt[location]['queueStreetResolution']='user_selected'
    else:attempt[location]='user_selected'
    self.assertEqual(e.confirmed_outcome(attempt,attempt['persistedPlace']),'confirmed_source_street');self.assertEqual(e.automatic_contribution(attempt),0)
    attempt['outcome']='confirmed_source_street';self.assertEqual(e.summary([result,attempt])['observedUIOfficialAutomatic'],1);self.assertEqual(e.summary([result,attempt])['observedUIConfirmedSourceStreet'],1)
 def test_public_manual_unconfirmed_mismatched_seeded_and_unknown_resolution_are_not_automatic(self):
  with tempfile.TemporaryDirectory() as folder:
   _,result,_,_,_=fixture(pathlib.Path(folder))
   for patch in [{'queueOrigin':'public'},{'queueOrigin':'manual'},{'queueConfirmed':False},{'queue':'1.1'},{'queueStreetResolution':'unknown'}]:
    attempt=copy.deepcopy(result);attempt['persistedPlace'].update(patch);self.assertEqual(e.automatic_contribution(attempt),0)
   for patch in [{'outcome':'harness_error'},{'queueEnteredManually':True},{'addressStorageSeeded':True},{'visibleQueue':None}]:self.assertEqual(e.automatic_contribution({**result,**patch}),0)
 def test_projection_retains_unknown_rows_and_original_dictionary_observation_without_reinterpretation(self):
  with tempfile.TemporaryDirectory() as folder:
   root=pathlib.Path(folder);case,result,state,place,capture=fixture(root);original=copy.deepcopy(place['queueCheckSourceEvidence']);proof=e.persist_projection(case,result,state,capture,root);raw=(root/proof['path']).read_bytes()
   self.assertEqual(json.loads(raw),original);self.assertEqual(e.sha(raw),proof['sha256']);self.assertEqual(len(raw),proof['bytes']);self.assertFalse(proof['independentlyVerified']);self.assertEqual(place['queueCheckSourceEvidence'],original);self.assertEqual(proof['readOnlyStateCapture']['sha256'],capture['sha256'])
 def test_projection_cannot_be_bound_to_another_frozen_case_apk_or_active_place(self):
  for mutation in ['case','apk','active','place']:
   with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as folder:
    root=pathlib.Path(folder);case,result,state,_,capture=fixture(root)
    if mutation=='case':result['id']='another-case'
    elif mutation=='apk':result['apkSha256']='unpinned'
    elif mutation=='active':state['activePlaceId']='other'
    else:result['persistedPlace']=copy.deepcopy(result['persistedPlace']);result['persistedPlace']['address']='different'
    with self.assertRaises(ValueError):e.persist_projection(case,result,state,capture,root)
 def test_stale_state_capture_tampered_database_and_capture_path_escape_are_rejected(self):
  for mutation in ['state','database','metadata','escape']:
   with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as folder:
    root=pathlib.Path(folder);case,result,state,place,capture=fixture(root)
    if mutation=='state':place['queueCheckSourceEvidence']['entries'][0]['rows'][0]['gpvRaw']='2.1'
    elif mutation=='database':(root/'database/capture-001/RKStorage').write_bytes(b'replaced original bytes')
    elif mutation=='metadata':(root/capture['path']).write_text('{}')
    else:capture={'path':'../outside/capture.json','sha256':'a'*64}
    with self.assertRaises(ValueError):e.persist_projection(case,result,state,capture,root)
 def test_fallback_or_changed_queue_cannot_reuse_an_earlier_complete_projection(self):
  for mutation in ['queue','adapter','status','cached','unsupported']:
   with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as folder:
    root=pathlib.Path(folder);case,result,state,place,_=fixture(root)
    if mutation=='queue':place['queue']='1.1'
    elif mutation=='adapter':place['queueCheckSourceEvidence']['resultBinding']['provider']='yasno'
    elif mutation=='status':place['queueCheckStatus']='source_unavailable'
    elif mutation=='cached':place['queueTransport']='public-cache'
    else:place['queueCheckSourceEvidence']['resultBinding']['provider']=None;place['queueCheckSourceEvidence']['unsupportedResult']=True
    capture=write_capture(root,state)
    with self.assertRaises(ValueError):e.persist_projection(case,result,state,capture,root)
 def test_incomplete_unsupported_and_missing_projections_are_explicit_not_primary_proofs(self):
  with tempfile.TemporaryDirectory() as folder:
   root=pathlib.Path(folder);case,result,state,place,_=fixture(root);projection=place['queueCheckSourceEvidence'];projection.update(complete=False,truncated=True,droppedEvents=2,unsupportedResult=True);projection['resultBinding']['provider']=None
   proof=e.persist_projection(case,result,state,write_capture(root,state),root);self.assertFalse(proof['captureComplete']);self.assertTrue(proof['truncated']);self.assertEqual(proof['droppedEvents'],2);self.assertFalse(proof['independentlyVerified'])
   place['queueCheckSourceEvidence']=None;proof=e.persist_projection(case,result,state,write_capture(root,state),root);self.assertEqual(proof['status'],'missing');self.assertTrue(proof['expectedForOperator'])
 def test_failed_current_check_is_preserved_without_reinterpreting_older_queue_provenance(self):
  with tempfile.TemporaryDirectory() as folder:
   root=pathlib.Path(folder);case,result,state,place,_=fixture(root);place.update(queueCheckStatus='source_unavailable',queueSource=None,queueTransport='public-cache');projection=place['queueCheckSourceEvidence'];projection.update(complete=False);projection['resultBinding'].update(status='source_unavailable',queue=None)
   proof=e.persist_projection(case,result,state,write_capture(root,state),root);self.assertEqual(proof['resultBinding']['status'],'source_unavailable');self.assertFalse(proof['captureComplete']);self.assertEqual(proof['independentQualificationStatus'],'pending')
 def test_oversized_or_non_json_projection_is_rejected_without_export(self):
  for value in ['x'*e.MAX_PROJECTION_BYTES,float('nan')]:
   with self.subTest(kind=type(value).__name__),tempfile.TemporaryDirectory() as folder:
    root=pathlib.Path(folder);case,result,state,place,_=fixture(root);place['queueCheckSourceEvidence']['extra']=value;capture=write_capture(root,state)
    with self.assertRaises(ValueError):e.persist_projection(case,result,state,capture,root)
    self.assertFalse((root/'public-source-projection.json').exists())
 def test_attempt_binding_hashes_original_result_screens_and_projection_without_rewriting_them(self):
  with tempfile.TemporaryDirectory() as folder:
   root=pathlib.Path(folder);case,result,state,_,capture=fixture(root);result['sourceEvidenceArtifact']=e.persist_projection(case,result,state,capture,root);(root/'result.json').write_bytes(e.encoded(result));(root/'queue-result.xml').write_bytes(b'<original/>');(root/'queue-result.png').write_bytes(b'original image bytes');original=(root/'result.json').read_bytes();binding=e.bind_attempt(case,result,root)
   self.assertEqual(binding['caseId'],case['id']);self.assertEqual(binding['apkSha256'],result['apkSha256']);self.assertEqual(binding['placeId'],state['activePlaceId']);self.assertEqual((root/'result.json').read_bytes(),original);self.assertEqual(next(x['sha256'] for x in binding['files'] if x['path']=='result.json'),e.sha(original))
   with self.assertRaises(ValueError):e.bind_attempt(case,{**result,'visibleQueue':'1.1'},root)
   (root/'public-source-projection.json').write_text('{}')
   with self.assertRaises(ValueError):e.bind_attempt(case,result,root)
 def test_real_wal_capture_retains_every_original_sidecar_and_reads_the_same_app_state(self):
  with tempfile.TemporaryDirectory() as folder:
   root=pathlib.Path(folder);case,result,state,_,_=fixture(root);source=root/'live';source.mkdir();directory=root/'database/capture-001'
   with sqlite3.connect(source/'RKStorage') as writer:
    writer.execute('PRAGMA journal_mode=WAL');writer.execute('CREATE TABLE catalystLocalStorage(key TEXT PRIMARY KEY,value TEXT)');writer.execute('INSERT INTO catalystLocalStorage VALUES (?,?)',('svitlo.state.v1',json.dumps(state)));writer.commit()
    for path in directory.iterdir():path.unlink()
    for path in source.iterdir():shutil.copyfile(path,directory/path.name)
    metadata={'readOnly':True,'readCompleted':True,'files':[{'path':p.name,'size':p.stat().st_size,'sha256':e.sha(p.read_bytes())} for p in sorted(directory.iterdir())]};proof=directory/'capture.json';proof.write_bytes(e.encoded(metadata));capture={'path':str(proof.relative_to(root)),'sha256':e.sha(proof.read_bytes())}
    with e.read_only_capture(directory/'RKStorage') as reader:self.assertEqual(json.loads(reader.execute('SELECT value FROM catalystLocalStorage').fetchone()[0]),state)
    saved=e.persist_projection(case,result,state,capture,root);self.assertEqual({pathlib.Path(p['path']).name for p in saved['readOnlyStateCapture']['files']},{'RKStorage','RKStorage-wal','RKStorage-shm'})
 def test_capture_completeness_never_qualifies_correctness_or_changes_the_denominator(self):
  with tempfile.TemporaryDirectory() as folder:
   root=pathlib.Path(folder);case,result,state,place,_=fixture(root);place['queueCheckSourceEvidence']['entries'][0]['rows'].append({'gpvRaw':'1.1','unknown':False});proof=e.persist_projection(case,result,state,write_capture(root,state),root)
   self.assertTrue(proof['captureComplete']);self.assertFalse(proof['independentlyVerified']);self.assertEqual(proof['independentQualificationStatus'],'pending')
   counts=e.summary([result,{**result,'outcome':'source_unavailable'},{**result,'outcome':'public_proposal_requires_confirmation'}]);self.assertEqual(counts['denominator'],3);self.assertEqual(counts['observedUIOfficialAutomatic'],1);self.assertIsNone(counts['independentlyQualifiedCorrect']);self.assertEqual(counts['independentQualificationStatus'],'pending')
if __name__=='__main__':unittest.main()
