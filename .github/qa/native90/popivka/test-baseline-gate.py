"""Negative controls for the narrowly observed old-parser baseline failure."""
import copy,datetime,hashlib,importlib.util,json,pathlib,tempfile,unittest
HERE=pathlib.Path(__file__).parent
def module(name,file):
 spec=importlib.util.spec_from_file_location(name,HERE/file);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
g=module('baseline_gate','baseline-gate.py');s=module('independent_source','source.py')
NOW=datetime.datetime(2026,11,25,10,tzinfo=datetime.timezone.utc)
def expected(raw):return {'date':'2026-11-25','observedAt':NOW.isoformat(),'queues':{'3.1':[[60,120]]},'versions':[{'date':'2026-11-25','order':0,'sourceUrl':'https://www.cherkasyoblenergo.com/media/example','sha256':hashlib.sha256(raw).hexdigest()}]}
def raw(body=None):return ('<html><main><nav>0 800 123456</nav><main><h1>ГПВ на25листопада</h1><p>'+(body or g.NEW_HEADER)+'</p></main><footer>Години відсутності електропостачання: 0 800 111222</footer></main></html>').encode()
def failure():return {'date':'2026-11-25','operatorId':'cherkasy','queue':'3.1','status':'unsupported_format','sourceUrl':'https://www.cherkasyoblenergo.com/off'}
ORIGINAL={'operatorId':'cherkasy','queue':'3.1'}
VISIBLE={'binding':'visible-graph-failure-title-and-detail'}
class BaselineGate(unittest.TestCase):
 def proof(self,directory,body=None):
  data=raw(body);(directory/'article-0.html').write_bytes(data);e=expected(data);return e,g.current_format_proof(e,directory,s.Document,NOW)
 def test_two_nested_mains_accept_only_the_unique_balanced_leaf_article_header(self):
  with tempfile.TemporaryDirectory() as folder:
   e,proof=self.proof(pathlib.Path(folder));self.assertEqual(proof['articles'][0]['globalMainCount'],2);self.assertEqual(proof['articles'][0]['articleScope'],'unique-balanced-leaf-main');result=g.known_failure(failure(),ORIGINAL,e,VISIBLE,proof);self.assertFalse(result['liveSchedulePassed']);self.assertTrue(result['failureObserved']);self.assertEqual(result['kind'],'observed-known-source-format-failure')
 def test_footer_outer_layout_multiple_leaf_or_unclosed_body_cannot_justify_a_baseline_failure(self):
  examples=[raw('інший розділ'),('<main><p>'+g.NEW_HEADER+'</p><main><p>тільки дата</p></main></main>').encode(),('<main><p>'+g.NEW_HEADER+'</p></main><main><p>'+g.NEW_HEADER+'</p></main>').encode(),('<main><main><p>'+g.NEW_HEADER+'</p></main>').encode()]
  with tempfile.TemporaryDirectory() as folder:
   p=pathlib.Path(folder)
   for data in examples:
    (p/'article-0.html').write_bytes(data)
    with self.subTest(html=data),self.assertRaises(AssertionError):g.current_format_proof(expected(data),p,s.Document,NOW)
 def test_current_raw_sha_date_and_observation_age_are_required(self):
  with tempfile.TemporaryDirectory() as folder:
   p=pathlib.Path(folder);e,_=self.proof(p)
   for patch in [{'date':'2026-11-24'},{'observedAt':(NOW-datetime.timedelta(minutes=11)).isoformat()},{'observedAt':(NOW+datetime.timedelta(minutes=1)).isoformat()}]:
    with self.subTest(patch=patch),self.assertRaises(AssertionError):g.current_format_proof({**e,**patch},p,s.Document,NOW)
   (p/'article-0.html').write_bytes(raw()+b' ')
   with self.assertRaises(AssertionError):g.current_format_proof(e,p,s.Document,NOW)
 def test_generic_source_errors_ready_data_or_wrong_saved_identity_never_pass_failure_gate(self):
  with tempfile.TemporaryDirectory() as folder:
   e,proof=self.proof(pathlib.Path(folder))
   for patch in [{'status':'source_unavailable'},{'status':'source_protected'},{'status':'ready'},{'queue':'3.2'},{'date':'2026-11-24'},{'operatorId':'other'},{'intervals':[{'start':'01:00','end':'02:00'}]},{'refreshError':{'status':'unsupported_format'}}]:
    with self.subTest(patch=patch),self.assertRaises(AssertionError):g.known_failure({**failure(),**patch},ORIGINAL,e,VISIBLE,proof)
   for visible in [None,{}, {'binding':'page-wide-message'}]:
    with self.assertRaises(AssertionError):g.known_failure(failure(),ORIGINAL,e,visible,proof)
   with self.assertRaises(AssertionError):g.known_failure(failure(),ORIGINAL,e,VISIBLE,{**proof,'verified':False})
 def test_ready_baseline_and_candidate_require_exact_current_official_intervals(self):
  e=expected(raw());snapshot={**failure(),'status':'ready','sourceUrl':e['versions'][0]['sourceUrl'],'provenance':'official','intervals':[{'start':'01:00','end':'02:00'}]};self.assertIs(g.live_snapshot(snapshot,ORIGINAL,e),snapshot)
  for patch in [{'intervals':[{'start':'01:00','end':'03:00'}]},{'refreshError':{'status':'source_unavailable'}},{'sourceUrl':'https://other.invalid/'},{'provenance':'public'},{'date':'2026-11-24'},{'queue':'1.1'}]:
   with self.subTest(patch=patch),self.assertRaises(AssertionError):g.live_snapshot({**snapshot,**patch},ORIGINAL,e)
 def test_upgrade_must_preserve_original_state_cache_and_appearance_before_launch(self):
  before={'activePlaceId':'original','places':[{'id':'original','reminders':{'enabled':False}}],'snapshots':{'original':{'today':failure()}},'notificationsEnabled':False};appearance={'version':1,'theme':'aurora'};g.unchanged_upgrade(before,copy.deepcopy(before),appearance,copy.deepcopy(appearance))
  for field,value in [('snapshots',{}),('activePlaceId','different'),('notificationsEnabled',True)]:
   with self.subTest(field=field),self.assertRaises(AssertionError):g.unchanged_upgrade(before,{**before,field:value},appearance,appearance)
  with self.assertRaises(AssertionError):g.unchanged_upgrade(before,before,appearance,{'version':1,'theme':'moss'})
 def test_offline_cache_can_add_only_refresh_error_without_renewal_or_data_change(self):
  snapshot={'date':'2026-11-25','queue':'3.1','status':'ready','checkedAt':'original','validUntil':123,'sourceUrl':'official','provenance':'official','intervals':[{'start':'01:00','end':'02:00'}],'historySlots':[{'start':0,'end':60,'type':'NotPlanned'}]};g.unchanged_offline_snapshot(snapshot,{**snapshot,'refreshError':{'status':'source_unavailable'}})
  for key in snapshot:
   with self.subTest(key=key),self.assertRaises(AssertionError):g.unchanged_offline_snapshot(snapshot,{**snapshot,key:None})
 def test_saved_settings_cannot_change_after_candidate_live_or_offline_restart(self):
  before={'notificationsEnabled':False,'gpsAsked':True,'endpoint':'','deleted':[],'pushToken':None};g.unchanged_settings(before,copy.deepcopy(before))
  for key in before:
   with self.subTest(key=key),self.assertRaises(AssertionError):g.unchanged_settings(before,{**before,key:'changed'})
  with self.assertRaises(AssertionError):g.unchanged_settings(before,{**before,'notificationsEnabled':0})
if __name__=='__main__':unittest.main()
