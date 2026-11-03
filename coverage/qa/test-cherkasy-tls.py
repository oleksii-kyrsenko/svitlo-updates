import importlib.util
import json
from pathlib import Path
import ssl
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
spec=importlib.util.spec_from_file_location('batch',Path(__file__).resolve().parents[1]/'batch-a.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class OfficialTLS(unittest.TestCase):
 def test_verified_public_intermediate_keeps_strict_hostname_and_chain_checks(self):
  context=m.cherkasy_tls_context()
  self.assertEqual(context.verify_mode,ssl.CERT_REQUIRED)
  self.assertTrue(context.check_hostname)

 def test_modified_certificate_and_failed_system_verification_stop_before_requests(self):
  certificate=Path(m.__file__).parent/'certificates/sectigo-dv-r36.pem'
  with patch.object(m.subprocess,'run',return_value=type('Result',(),{'returncode':1})()):
   with self.assertRaisesRegex(ValueError,'system_root_verification_failed'):m.cherkasy_tls_context()
  with tempfile.TemporaryDirectory() as temp:
   changed=Path(temp)/'changed.pem';der=ssl.PEM_cert_to_DER_cert(certificate.read_text());changed.write_text(ssl.DER_cert_to_PEM_cert(der[:-1]+bytes([der[-1]^1])))
   with self.assertRaisesRegex(ValueError,'fingerprint_mismatch'):m.cherkasy_tls_context(changed)

 def test_only_exact_official_https_api_receives_the_completed_chain(self):
  handler=m.CherkasyHTTPSHandler()
  official='https://cabinet.cherkasyoblenergo.com/api_new/disconn.php?op=department_list'
  urls=[official,official.replace('cabinet.','other.'),official.replace('/api_new/disconn.php','/other'),official.replace('cabinet.','cabinet.user@'),official.replace('.com/','.com:444/')]
  seen=[]
  handler.do_open=lambda cls,req,**kw:seen.append(kw)
  for url in urls:handler.https_open(m.urllib.request.Request(url))
  self.assertIs(seen[0]['context'],handler.official_context)
  self.assertTrue(all(item['context'] is None for item in seen[1:]))
  self.assertTrue(all(item['check_hostname'] for item in seen))

 def test_collector_errors_never_retain_account_queries_or_exception_text(self):
  collector=m.Collector('cherkasy',geography=object())
  collector.error('collection',ValueError('https://cabinet.cherkasyoblenergo.com/api_new/disconn.php?abon_ls=private-subscriber'))
  text=json.dumps(collector.errors)
  self.assertNotIn('private-subscriber',text)
  self.assertNotIn('abon_ls',text)
  self.assertEqual(collector.errors,[{'stage':'collection','error':'ValueError','httpStatus':None}])


if __name__=='__main__':unittest.main()
