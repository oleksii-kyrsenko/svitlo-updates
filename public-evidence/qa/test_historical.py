"""Synthetic controls: no production address or queue fixtures."""
import asyncio,contextlib,copy,hashlib,importlib.util,io,json,pathlib,sys,tempfile,types,unittest
from unittest.mock import AsyncMock,patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'historical'))
from importer import DAY,MAX_SOURCE_AGE,collect,compact,house_key,import_snapshot,merge_records,monitor_revision,source_url,street_keys

class Historical(unittest.TestCase):
 now=1793943000000
 def fixture(self,streets=None):
  data={'meta':{'region_code':'UA-00','dso_code':'synthetic'},'settlements':{'test/key~1':{'name':'Навчальне','type':'м.','hromada':'Навчальна громада','katottg':'UA00000000000000000','streets':streets or {'вул. Навчальна':{'1':['1.1'],'2':['2.1']}},'gav':{'вул. Навчальна':{'3':['9']}}}}}
  source={'id':'synthetic','format':'settlements-streets-gpv-v1','repository':'example/synthetic','commit':'a'*40,'path':'snapshot.json','publishedCommit':'b'*40,'publishedAt':self.now-30*DAY,'operatorId':'synthetic','regionId':'UA-00','sourceDsoCode':'synthetic','settlement':'Навчальне','community':'Навчальна громада','katottg':'UA00000000000000000'}
  return data,source
 def run_import(self,data,source):
  raw=compact(data).encode();source={**source,'sha256':hashlib.sha256(raw).hexdigest()};return import_snapshot(raw,source,self.now)
 def test_exact_projected_quotes_pointer_and_original_date(self):
  d,s=self.fixture();records,stats=self.run_import(d,s);self.assertEqual(stats['acceptedHouses'],2)
  r=records[0];self.assertEqual(r['publishedAt'],s['publishedAt']);self.assertEqual(r['sourceSnapshot']['publishedAt'],r['publishedAt']);self.assertTrue(r['historical']);self.assertTrue(r['requiresConfirmation']);self.assertEqual(r['method'],'direct');self.assertEqual(r['evidenceType'],'historical-directory');self.assertNotIn('adapter',r)
  self.assertEqual(r['sourceSnapshot']['jsonPointer'],'/settlements/test~1key~01/streets/вул. Навчальна');self.assertEqual(json.loads(r['quote']),{'вул. Навчальна':{'1':['1.1']}});self.assertEqual(json.loads(r['sourceContext']['quote']),{'name':'Навчальне','hromada':'Навчальна громада','katottg':s['katottg']})
 def test_empty_multi_wrong_type_and_normalized_conflict_veto_before_filter(self):
  for other in [[],['1.1','2.1'],['9'],None,'1.1',['2.1']]:
   d,s=self.fixture({'вул. Навчальна':{'1А':['1.1'],'１а':other,'2':['2.1']}});rs,_=self.run_import(d,s);self.assertEqual([h for r in rs for h in r['houses']],['2'])
 def test_malformed_selector_retracts_entire_street_without_expansion(self):
  for selector in ['1, 3','1–3','1-3','1 к2','1/2, корпус 3','1 (непарні)']:
   d,s=self.fixture({'вул. Навчальна':{'1':['1.1'],selector:['1.1']}});self.assertEqual(self.run_import(d,s)[0],[])
 def test_normalized_street_collision_never_selects_a_convenient_alias(self):
  d,s=self.fixture({'вул. Навчальна':{'1':['1.1']},'Навчальна вулиця':{'2':[]}});self.assertEqual(self.run_import(d,s)[0],[])
 def test_same_house_same_queue_deduplicates_without_rewriting_literal(self):
  d,s=self.fixture({'вул. Навчальна':{'1А':['1.1'],'1а':['1.1']}});rs,stats=self.run_import(d,s);self.assertEqual(rs[0]['houses'],['1А']);self.assertEqual(stats['duplicateEquivalentHouses'],1)
 def test_suffix_slash_exact_and_latin_cyrillic_stay_distinct(self):
  d,s=self.fixture({'вул. Навчальна':{'1А':['1.1'],'1A':[],'2/3Б':['2.1']}});rs,_=self.run_import(d,s);self.assertEqual({h for r in rs for h in r['houses']},{'1А','2/3Б'});self.assertNotEqual(house_key('1А'),house_key('1A'))
 def test_gav_and_another_settlement_cannot_supply_gpv(self):
  d,s=self.fixture();d['settlements']['other']={**d['settlements']['test/key~1'],'name':'Інше','katottg':'UA00000000000000001','streets':{'вул. Чужа':{'1':['6.2']}}};rs,_=self.run_import(d,s);self.assertEqual({h for r in rs for h in r['houses']},{'1','2'});self.assertFalse(any(r['street']=='вул. Чужа' for r in rs))
 def test_hash_duplicate_json_keys_and_geography_fail_closed(self):
  d,s=self.fixture();raw=compact(d).encode();s['sha256']='0'*64
  with self.assertRaisesRegex(ValueError,'hash'):import_snapshot(raw,s,self.now)
  raw=b'{"meta":{},"meta":{}}';s['sha256']=hashlib.sha256(raw).hexdigest()
  with self.assertRaisesRegex(ValueError,'Duplicate'):import_snapshot(raw,s,self.now)
  d,s=self.fixture();d['meta']['dso_code']='other'
  with self.assertRaisesRegex(ValueError,'binding'):self.run_import(d,s)
 def test_original_max_age_and_offline_expiry_cannot_be_refreshed(self):
  d,s=self.fixture();s['publishedAt']=self.now-MAX_SOURCE_AGE-DAY
  with self.assertRaisesRegex(ValueError,'180-day'):self.run_import(d,s)
  s['publishedAt']=self.now-MAX_SOURCE_AGE+DAY;rs,_=self.run_import(d,s);self.assertEqual(rs[0]['expiresAt'],self.now+DAY)
 def test_successful_reread_changes_only_observation_clock(self):
  d,s=self.fixture();raw=compact(d).encode();s['sha256']=hashlib.sha256(raw).hexdigest();a,_=import_snapshot(raw,s,self.now);b,_=import_snapshot(raw,s,self.now+DAY);self.assertEqual(a[0]['id'],b[0]['id']);self.assertEqual(a[0]['publishedAt'],b[0]['publishedAt']);self.assertEqual(b[0]['fetchedAt']-a[0]['fetchedAt'],DAY)
 def test_chunks_bound_houses_and_json_quote_bytes(self):
  d,s=self.fixture({'вул. Навчальна':{str(i):['1.1'] for i in range(1,251)}});rs,_=self.run_import(d,s);self.assertEqual(sum(len(r['houses']) for r in rs),250)
  for r in rs:self.assertLessEqual(len(r['houses']),100);self.assertLessEqual(len(r['quote'].encode()),2500);self.assertEqual(list(json.loads(r['quote'])[r['street']]),r['houses'])
 def test_merge_preserves_other_pipeline_records_and_retracts_old_snapshot(self):
  d,s=self.fixture();rs,_=self.run_import(d,s);old={'schemaVersion':2,'enabled':False,'generatedAt':1,'records':[{'id':'other','evidenceType':'section-roster','publishedAt':7},{'id':'removed','evidenceType':'historical-directory','sourceUrl':rs[0]['sourceUrl']}]};new=merge_records(old,rs,{rs[0]['sourceUrl']},self.now);self.assertFalse(new['enabled']);self.assertEqual(new['records'][0],old['records'][0]);self.assertNotIn('removed',[r['id'] for r in new['records']])
 def test_failed_fetch_cannot_renew_a_previous_record(self):
  d,s=self.fixture();raw=compact(d).encode();s['sha256']=hashlib.sha256(raw).hexdigest();rs,_=import_snapshot(raw,s,self.now);old={'schemaVersion':2,'enabled':True,'records':rs};before=copy.deepcopy(old)
  def fail(_):raise ValueError('unavailable')
  with self.assertRaisesRegex(ValueError,'previous manifest retained'):collect({'schemaVersion':1,'enabled':True,'sources':[s]},old,self.now+DAY,fail)
  self.assertEqual(old,before)
 def test_new_reviewed_pin_replaces_family_and_preserves_other_city(self):
  d,s=self.fixture();old_records,_=self.run_import(d,s);other=copy.deepcopy(old_records[0]);other.update(id='other-city',katottg='UA00000000000000001')
  s.update(commit='c'*40,publishedCommit='d'*40,publishedAt=self.now-DAY);d['settlements']['test/key~1']['streets']={'вул. Навчальна':{'3':['2.2']}};raw=compact(d).encode();s['sha256']=hashlib.sha256(raw).hexdigest();old={'schemaVersion':2,'enabled':True,'records':old_records+[other]};new,report=collect({'schemaVersion':1,'enabled':True,'sources':[s]},old,self.now,lambda _:raw)
  self.assertEqual(len(new['records']),2);self.assertIn(other,new['records']);self.assertEqual(new['records'][-1]['publishedAt'],s['publishedAt']);self.assertEqual(new['records'][-1]['houses'],['3']);self.assertNotIn(old_records[0],new['records'])
 def test_mixed_success_withdraws_empty_family_without_renewing_failed_family(self):
  d,s=self.fixture();old,_=self.run_import(d,s);failed=copy.deepcopy(old[0]);failed.update(id='failed',katottg='UA00000000000000001');failed['fetchedAt']=self.now-DAY
  good={**s,'commit':'c'*40};d['settlements']['test/key~1']['streets']={'вул. Навчальна':{'1':[]}};raw=compact(d).encode();good['sha256']=hashlib.sha256(raw).hexdigest();bad={**good,'id':'failed-source','katottg':failed['katottg']}
  def read(source):
   if source['id']=='failed-source':raise ValueError('unavailable')
   return raw
  result,report=collect({'schemaVersion':1,'enabled':True,'sources':[good,bad]},{'schemaVersion':2,'enabled':True,'records':old+[failed]},self.now,read)
  self.assertEqual(result['records'],[failed]);self.assertEqual(len(report['errors']),1)
 def test_disable_retracts_only_historical_reader(self):
  old={'schemaVersion':2,'enabled':True,'records':[{'id':'other'},{'id':'historical','evidenceType':'historical-directory','sourceUrl':'old'}]};new,report=collect({'schemaVersion':1,'enabled':False,'sources':[{},{}]},old,self.now);self.assertEqual(new['records'],[{'id':'other'}]);self.assertTrue(new['enabled']);self.assertEqual(report['serializedBytes'],len((compact(new)+'\n').encode()))
 def test_client_normalization_golden_cases(self):
  self.assertEqual(street_keys(['вул. Навчальна','Навчальна вулиця','пров. Навчальна','Навчальна провулок','майдан Навчальний','площа Навчальний','вул. П’ятнична','вул. Пятнична']),['навчальна','навчальна','навчальна|lane','навчальна|lane','навчальний|square','навчальний|square','пятнична','пятнична'])
 def test_whole_dataset_size_limit_cannot_silently_truncate(self):
  old={'schemaVersion':2,'records':[{'id':'huge','quote':'x'*2_000_000}]}
  with self.assertRaisesRegex(ValueError,'byte budget'):merge_records(old,[],set(),self.now)
 def test_existing_agents_writer_preserves_historical_dates_and_compact_budget(self):
  sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]));import agents
  d,s=self.fixture();records,_=self.run_import(d,s);old_root,old_now=agents.ROOT,agents.NOW
  try:
   with tempfile.TemporaryDirectory() as tmp:
    root=pathlib.Path(tmp);agents.ROOT=root;agents.NOW=lambda:self.now
    (root/'sources.json').write_text(compact({'enabled':True,'official':[],'community':[],'discovery':[],'searches':[],'documents':[]}))
    (root/'manifest.json').write_text(compact({'schemaVersion':2,'enabled':True,'records':records}))
    with contextlib.redirect_stdout(io.StringIO()):agents.collect()
    raw=(root/'manifest.json').read_bytes();result=json.loads(raw);self.assertEqual(result['records'],records);self.assertNotIn(b'\n  ',raw);self.assertLessEqual(len(raw),2_000_000)
  finally:agents.ROOT,agents.NOW=old_root,old_now
 def test_exact_age_boundary_and_spaced_house_are_not_unusable_runtime_records(self):
  d,s=self.fixture();s['publishedAt']=self.now-MAX_SOURCE_AGE
  with self.assertRaisesRegex(ValueError,'180-day'):self.run_import(d,s)
  d,s=self.fixture({'вул. Навчальна':{' 1':['1.1'],'2':['2.1']}});self.assertEqual(self.run_import(d,s)[0],[])
 def test_config_cannot_select_two_pins_for_one_source_family(self):
  d,s=self.fixture();raw=compact(d).encode();s['sha256']=hashlib.sha256(raw).hexdigest()
  for enabled in ['false',1,None]:
   with self.assertRaisesRegex(ValueError,'controls'):collect({'schemaVersion':1,'enabled':enabled,'sources':[s]},{'schemaVersion':2,'records':[]},self.now,lambda _:raw)
  with self.assertRaisesRegex(ValueError,'unique'):collect({'schemaVersion':1,'enabled':True,'sources':[s,{**s,'commit':'c'*40}]},{'schemaVersion':2,'records':[]},self.now,lambda _:raw)
 def test_news_scan_cannot_retract_another_readers_record_at_the_same_url(self):
  sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]));import agents,history
  d,s=self.fixture();records,_=self.run_import(d,s);directory={**records[0],'id':'live-directory','recordVersion':3,'evidenceType':'address-directory'}
  with tempfile.TemporaryDirectory() as tmp,patch.object(agents,'ROOT',pathlib.Path(tmp)),patch.object(agents,'NOW',lambda:self.now),patch.object(history,'read_articles',return_value=([],{'readUrls':[records[0]['sourceUrl']]})):
   root=pathlib.Path(tmp);(root/'sources.json').write_text(compact({'enabled':True,'official':[],'community':[{'url':records[0]['sourceUrl']}],'discovery':[],'searches':[],'documents':[]}));(root/'manifest.json').write_text(compact({'schemaVersion':2,'enabled':True,'records':records+[directory]}))
   with contextlib.redirect_stdout(io.StringIO()):agents.collect()
   self.assertEqual(json.loads((root/'manifest.json').read_text())['records'],records+[directory])
 def test_rollback_writers_keep_the_complete_historical_manifest_under_client_limit(self):
  from manifest_io import MAX_BYTES
  def load(name,path):
   spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
  base=pathlib.Path(__file__).resolve().parents[1];global_disable=load('global_disable',base/'disable.py');directory_disable=load('directory_disable',base/'directory/disable.py')
  records=[{'id':str(i),'evidenceType':'historical-directory','quote':'ю'*650,'publishedAt':self.now-30*DAY,'fetchedAt':self.now} for i in range(1000)]
  for reader in [global_disable,directory_disable]:
   with tempfile.TemporaryDirectory() as tmp:
    root=pathlib.Path(tmp);(root/'directory').mkdir();(root/'sources.json').write_text('{"enabled":true}');(root/'manifest.json').write_text(compact({'schemaVersion':2,'enabled':True,'records':records}));(root/'directory/sources.json').write_text('[{"id":"old"}]');reader.disable(root);raw=(root/'manifest.json').read_bytes();self.assertLessEqual(len(raw),MAX_BYTES);self.assertEqual(json.loads(raw)['records'],records)
 def test_atomic_manifest_failure_and_oversize_never_replace_previous_bytes(self):
  import manifest_io
  with tempfile.TemporaryDirectory() as tmp:
   root=pathlib.Path(tmp);path=root/'manifest.json';old=b'{"schemaVersion":2,"enabled":false,"records":[]}';path.write_bytes(old)
   with patch.object(manifest_io.os,'replace',side_effect=OSError('replace denied')):
    with self.assertRaisesRegex(OSError,'replace denied'):manifest_io.write_manifest(path,{'schemaVersion':2,'enabled':True,'records':[]})
   self.assertEqual(path.read_bytes(),old);self.assertEqual(list(root.iterdir()),[path])
   with self.assertRaisesRegex(ValueError,'record budget'):manifest_io.write_manifest(path,{'schemaVersion':2,'records':[{}]*10001})
   self.assertEqual(path.read_bytes(),old)
 def test_changed_upstream_is_a_review_lead_and_cannot_renew_a_publication(self):
  d,s=self.fixture();raw=compact(d).encode();s['sha256']=hashlib.sha256(raw).hexdigest();before=copy.deepcopy(s)
  blob=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
  for sha in [blob,'f'*40]:
   response=io.BytesIO(compact({'sha':sha}).encode())
   with patch('importer.urllib.request.urlopen',return_value=response):report=monitor_revision(s,raw)
   self.assertEqual(report['changed'],sha!=blob);self.assertEqual(report['action'],'review-new-pin-and-original-publication' if sha!=blob else 'unchanged-publication');self.assertEqual(s,before)
 def test_live_directory_writer_preserves_historical_reader_provenance(self):
  d,s=self.fixture();records,_=self.run_import(d,s);url=records[0]['sourceUrl']
  page=types.SimpleNamespace(url=url,goto=AsyncMock(return_value=types.SimpleNamespace(status=200)),content=AsyncMock(return_value='<html/>'))
  context=types.SimpleNamespace(new_page=AsyncMock(return_value=page),close=AsyncMock());browser=types.SimpleNamespace(new_context=AsyncMock(return_value=context),close=AsyncMock());playwright=types.SimpleNamespace(chromium=types.SimpleNamespace(launch=AsyncMock(return_value=browser)))
  class Manager:
   async def __aenter__(self):return playwright
   async def __aexit__(self,*_):return False
  fake=types.ModuleType('playwright.async_api');fake.async_playwright=lambda:Manager()
  base=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(base/'directory'))
  with patch.dict(sys.modules,{'playwright':types.ModuleType('playwright'),'playwright.async_api':fake}):
   spec=importlib.util.spec_from_file_location('directory_collect_control',base/'directory/collect.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  with tempfile.TemporaryDirectory() as tmp:
   root=pathlib.Path(tmp);(root/'directory').mkdir();(root/'sources.json').write_text('{"enabled":true}');(root/'directory/sources.json').write_text(compact([{'url':url}]));(root/'manifest.json').write_text(compact({'schemaVersion':2,'enabled':True,'records':records}))
   with patch.object(module,'ROOT',root),patch.object(module,'__file__',str(root/'directory/collect.py')),patch.object(module.time,'time',return_value=self.now/1000),patch.object(module,'street_links',return_value=[{'url':url,'label':'Навчальна'}]),patch.object(module,'observe',return_value=None),contextlib.redirect_stdout(io.StringIO()):asyncio.run(module.collect())
   raw=(root/'manifest.json').read_bytes();self.assertEqual(json.loads(raw)['records'],records);self.assertNotIn(b'\n  ',raw)
if __name__=='__main__':unittest.main()
