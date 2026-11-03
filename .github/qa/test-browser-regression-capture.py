import base64,importlib.util,json,tempfile,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('capture',Path(__file__).with_name('browser-regression-capture.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Response:
 def __init__(self,value,status=200):self.value=value;self.status=status;self.headers={'content-type':'application/json'}
 def body(self):return json.dumps(self.value).encode() if not isinstance(self.value,bytes) else self.value
class Request:
 def __init__(self,response):self.response=response;self.calls=[]
 def fetch(self,url,**options):self.calls.append((url,options));return self.response
class Context:
 def __init__(self,response):self.request=Request(response)
class CaptureControls(unittest.TestCase):
 def capture(self,tmp,response):return m.Capture(Context(response),None,Path(tmp),limit=8)
 def test_subscriber_lists_lose_names_ids_and_dictionary_keys(self):
  ids={};raw='991122334455';value=m.sanitize(m.CHERKASY_API+'?op=ls_list_by_addr',{raw:{'LS':raw,'NAME':'Private customer','EIC':'56XS123456789012'}},ids)
  self.assertEqual(value,[{'LS':'qa-account-1'}]);self.assertEqual(ids[raw],'qa-account-1');self.assertNotIn(raw,json.dumps(value));self.assertNotIn('Private',json.dumps(value))
 def test_queue_reply_removes_private_fields_and_known_identifiers_inside_text(self):
  value=m.sanitize(m.CHERKASY_API+'?op=disconn_by_ls',{'NAME':'Private','DISCONN_QUEUQ':[{'QUEUE_INFO':'991122334455; ГПВ:4.1 56XS123456789012','LS':'991122334455'}]},{'991122334455':'qa-account-1'})
  self.assertEqual(value['DISCONN_QUEUQ'][0]['QUEUE_INFO'],'[redacted-account]; ГПВ:4.1 [redacted-eic]')
 def test_dtek_reply_keeps_only_public_house_and_queue_fields(self):
  value=m.sanitize(m.DTEK+'/ua/ajax',{'result':True,'data':{'52':{'sub_type_reason':['GPV5.2'],'EIC':'secret','customer':'Private'}}},{})
  self.assertEqual(value,{'result':True,'data':{'52':{'sub_type_reason':['GPV5.2']}}})
 def test_dictionary_fields_are_explicit_and_do_not_keep_customer_metadata(self):
  value=m.sanitize(m.CHERKASY_API+'?op=city_list',{'1':{'ID':'1','NAME':'Черкаси','postcode':'18000','LS':'private','customerName':'Private'}},{})
  self.assertEqual(value,[{'ID':'1','NAME':'Черкаси','postcode':'18000'}])
 def test_real_account_url_is_used_only_for_network_not_artifact(self):
  with tempfile.TemporaryDirectory() as tmp:
   c=self.capture(tmp,Response({'DISCONN_QUEUQ':[{'QUEUE_INFO':'ГПВ4.1','LS':'991122334455'}]}));public=m.CHERKASY_API+'?abon_ls=qa-account-1&op=disconn_by_ls';private=m.CHERKASY_API+'?abon_ls=991122334455&op=disconn_by_ls'
   c.request(public,m.CHERKASY_HEADERS,network_url=private)
   self.assertIn('991122334455',c.context.request.calls[0][0])
   for path in Path(tmp).iterdir():self.assertNotIn('991122334455',path.read_text())
   self.assertNotIn('991122334455',json.dumps(c.entries));self.assertNotIn('991122334455',json.dumps(c.proofs))
 def test_private_error_html_never_leaks_account_in_server_error_page(self):
  with tempfile.TemporaryDirectory() as tmp:
   c=self.capture(tmp,Response(b'<html>Error account991122334455</html>',503));url=m.CHERKASY_API+'?op=disconn_by_ls&abon_ls=qa-account-1'
   with self.assertRaisesRegex(m.Stop,'official-http-503'):c.request(url,m.CHERKASY_HEADERS)
   self.assertNotIn('991122334455',''.join(p.read_text() for p in Path(tmp).iterdir()));self.assertNotIn('991122334455',base64.b64decode(c.entries[0]['bodyBase64']).decode())
 def test_unknown_host_and_credentials_are_rejected_before_network(self):
  with tempfile.TemporaryDirectory() as tmp:
   c=self.capture(tmp,Response({}))
   for url,headers in [('https://example.org/data',{}),(m.DTEK+'/ua/ajax',{'Cookie':'secret'}),('https://user:secret@www.dtek-dnem.com.ua/ua/ajax',{}),(m.DTEK+'/login',{})]:
    with self.assertRaises(m.Stop):c.request(url,headers)
   self.assertEqual(c.context.request.calls,[])
 def test_source_response_budget_fails_before_reading_payload(self):
  with tempfile.TemporaryDirectory() as tmp:
   response=Response({});response.headers['content-length']=str(m.MAX_RESPONSE+1);c=self.capture(tmp,response)
   with self.assertRaisesRegex(m.Stop,'source-response-budget'):c.request(m.DTEK+'/ua/shutdowns',m.COMMON)
 def test_data_assignment_is_parsed_not_executed_or_invented(self):
  self.assertEqual(m.assignment('DisconSchedule.streets = {"місто":["Нова"]};','DisconSchedule.streets'),{'місто':['Нова']})
  for value in ['<script>challenge</script>','DisconSchedule.streets = doSomething();']:
   with self.assertRaises(m.Stop):m.assignment(value,'DisconSchedule.streets')
 def test_frozen_inputs_do_not_include_saved_or_expected_queues(self):
  p=Path(__file__).with_name('browser-regression-inputs.json');inputs=json.loads(p.read_text());self.assertEqual(len(inputs['cases']),3)
  def check(value):
   if isinstance(value,dict):
    self.assertFalse(any(k in ['queue','expectedQueue','queueConfirmed','queueOrigin'] for k in value))
    for v in value.values():check(v)
   elif isinstance(value,list):
    for v in value:check(v)
  check(inputs)
 def test_exact_houses_do_not_collapse_letters_or_fractions(self):
  self.assertEqual(m.house_key('2-К'),m.house_key('2К'));self.assertEqual(m.house_key('1A'),m.house_key('1-А'))
  self.assertNotEqual(m.house_key('1/2'),m.house_key('12'));self.assertNotEqual(m.house_key('2'),m.house_key('2К'))
 def test_errors_do_not_print_request_urls_account_or_exception_body(self):
  self.assertEqual(m.clean_error(RuntimeError('https://example.org?abon_ls=private'))['reason'],'official-request-failed')
 def test_request_diagnostics_retain_only_safe_fixed_codes(self):
  samples=[('net::ERR_CERT_AUTHORITY_INVALID at https://example.org?abon_ls=private','official-tls-certificate-error'),('SSL_ERROR_UNSUPPORTED_VERSION private','official-tls-protocol-error'),('Request timed out private','official-request-timeout'),('getaddrinfo ENOTFOUND private','official-dns-unavailable'),('ECONNRESET private','official-connection-reset'),('Something private','official-request-unavailable')]
  for message,expected in samples:
   self.assertEqual(m.request_failure(RuntimeError(message)),expected);self.assertNotIn('private',m.request_failure(RuntimeError(message)))
if __name__=='__main__':unittest.main()
