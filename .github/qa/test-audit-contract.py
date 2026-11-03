"""Controls for a public binary/UI audit; no emulator or application imports."""
import copy,hashlib,importlib.util,json,pathlib,tempfile,unittest

def load(name):
 p=pathlib.Path(__file__).with_name(name+'.py');spec=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
contract=load('audit-contract');audit=load('national-address-audit')
class ContractChecks(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name)
  (self.root/'sample.json').write_text(json.dumps({'cases':[{'id':f'UA-30-holdout-{i}','regionId':'UA-30'} for i in range(1,21)]}))
  self.request={'regions':['UA-30'],'limit':20,'sample':'sample.json','sampleSha256':contract.sha256(self.root/'sample.json')}
 def tearDown(self):self.tmp.cleanup()
 def test_twenty_cases_split_once_in_original_frozen_order(self):
  c,m=contract.plan(self.request,self.root);chunks=m['include'];self.assertEqual(len(chunks),4)
  self.assertEqual([v for chunk in chunks for v in chunk['caseIds'].split(',')],[f'UA-30-holdout-{i}' for i in range(1,21)])
  self.assertEqual(c['apkSha256'],contract.DEFAULT['apkSha256']);self.assertEqual(c['versionCode'],88)
 def test_mutated_sample_and_case_substitution_fail(self):
  bad=copy.deepcopy(self.request);bad['sampleSha256']='0'*64
  self.assertRaises(ValueError,contract.plan,bad,self.root)
  bad=copy.deepcopy(self.request);bad['caseIds']=['another-case'];self.assertRaises(ValueError,contract.plan,bad,self.root)
 def test_sample_escape_and_binary_inputs_fail_closed(self):
  for patch in [{'sample':'../sample.json'},{'androidApi':34},{'chunkSize':6},{'apkUrl':'https://user:pass@example.org/a.apk'},{'apkSha256':'bogus'},{'versionCode':0}]:
   self.assertRaises(ValueError,contract.contract,{**self.request,**patch},self.root)
 def test_requested_apk_bytes_certificate_and_package_must_all_match(self):
  apk=self.root/'a.apk';apk.write_bytes(b'fixture-apk');c=contract.contract({**self.request,'apkSize':apk.stat().st_size,'apkSha256':contract.sha256(apk)},self.root)
  sdk=self.root/'sdk';b=sdk/'build-tools'/'36.0.0';b.mkdir(parents=True)
  for name in ['apksigner','aapt']:(b/name).touch()
  def runner(args,**kwargs):
   if args[0].endswith('/apksigner'):return 'Signer #1 certificate SHA-256 digest: '+contract.CERTIFICATE+'\n'
   return "package: name='ua.svitlo.app.testing' versionCode='88' versionName='0.1.52' platformBuildVersionName='16'\n"
  self.assertTrue(contract.verify_apk(apk,c,sdk,runner)['signatureVerified'])
  self.assertRaises(ValueError,contract.verify_apk,apk,{**c,'apkSha256':'0'*64},sdk,runner)
  def wrong_cert(args,**kwargs):return 'Signer #1 certificate SHA-256 digest: '+'0'*64
  self.assertRaises(ValueError,contract.verify_apk,apk,c,sdk,wrong_cert)
  self.assertRaises(ValueError,contract.verify_apk,apk,{**c,'versionCode':89},sdk,runner)


class SignerFormatChecks(unittest.TestCase):
 def test_sdk_signer_formats_keep_exact_certificate_pin(self):
  pin=contract.CERTIFICATE
  colon=':'.join(pin[i:i+2] for i in range(0,len(pin),2)).upper()
  for label,value in [('Signer #1',pin),('Signer #1 (minSdkVersion=24, maxSdkVersion=36)',colon),('Signer (minSdkVersion=24, maxSdkVersion=36)',pin.upper())]:
   self.assertEqual(contract.signing_certificate('Number of signers: 1\n'+label+' certificate SHA-256 digest: '+value+'\n'),pin)
 def test_other_fingerprints_cannot_replace_actual_signer(self):
  pin=contract.CERTIFICATE
  for text in ['Signer #1 public key SHA-256 digest: '+pin,'Source Stamp Signer certificate SHA-256 digest: '+pin,'Signer #1 certificate SHA-256 digest: '+'0'*64+'\nSource Stamp Signer certificate SHA-256 digest: '+pin,'Signer #2 certificate SHA-256 digest: '+pin]:
   self.assertRaises(ValueError,contract.signing_certificate,text)
 def test_multiple_and_truncated_signers_are_rejected(self):
  line='Signer #1 certificate SHA-256 digest: '+contract.CERTIFICATE+'\n'
  for text in [line+line,line+line.replace('#1','#2'),line+'Signer #2 certificate SHA-256 digest: malformed\n','Number of signers: 2\n'+line,line[:-3]]:
   self.assertRaises(ValueError,contract.signing_certificate,text)
 def test_stable_native_build_tools_take_precedence_over_preview(self):
  with tempfile.TemporaryDirectory() as tmp:
   sdk=pathlib.Path(tmp)
   for version in ['35.0.0','36.0.0','37.0.0-rc2']:
    b=sdk/'build-tools'/version;b.mkdir(parents=True)
    for name in ['aapt','apksigner']:(b/name).touch()
   self.assertEqual(contract.tools(sdk).name,'36.0.0')
 def test_signature_failure_retains_actual_output_and_selected_tool(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=pathlib.Path(tmp);apk=root/'fixture.apk';apk.write_bytes(b'fixture')
   sdk=root/'sdk';tools=sdk/'build-tools'/'36.0.0';tools.mkdir(parents=True)
   for name in ['aapt','apksigner']:(tools/name).touch()
   c={**contract.DEFAULT,'apkSize':apk.stat().st_size,'apkSha256':contract.sha256(apk)}
   signature='Signer #1 certificate SHA-256 digest: '+'0'*64+'\n'
   def runner(*args,**kwargs):return signature
   proof=root/'proof'
   self.assertRaises(ValueError,contract.verify_apk,apk,c,sdk,runner,proof)
   self.assertEqual((proof/'signature-output.txt').read_text(),signature)
   self.assertEqual(json.loads((proof/'verification-tools.json').read_text())['buildTools'],'36.0.0')

class VisibleAddressChecks(unittest.TestCase):
 def setUp(self):
  self.case={'city':'Зразок','exactStreet':'вулиця Нова','exactHouse':'7-А'}
  self.place={'addressOrigin':'structured','addressParts':{'settlement':'Зразок','street':'вулиця Нова','house':'7-А'},'addressSelection':{'city':{'id':'city-1'},'street':{'name':'вулиця Нова','id':None,'manual':True,'source':'user'},'house':{'name':'7-А','id':None,'manual':True}}}
  self.result={'streetEnteredThroughUI':True,'houseEnteredThroughUI':True}
 def test_manual_street_requires_visible_action_and_preserves_exact_house(self):
  audit.validate_saved_address(self.case,self.result,self.place)
  self.assertRaises(RuntimeError,audit.validate_saved_address,self.case,{'houseEnteredThroughUI':True},self.place)
  changed=copy.deepcopy(self.place);changed['addressParts']['house']='7';self.assertRaises(RuntimeError,audit.validate_saved_address,self.case,self.result,changed)
  changed=copy.deepcopy(self.place);changed['addressParts']['street']='провулок Нова';self.assertRaises(RuntimeError,audit.validate_saved_address,self.case,self.result,changed)
 def test_official_roster_selection_is_valid_without_postal_house_id(self):
  p=copy.deepcopy(self.place);p['addressSelection']['street']={'id':'official:street-1','name':'вулиця Нова','source':'official-roster'};p['addressSelection']['house']={'name':'7-А','id':None,'source':'official-roster'}
  audit.validate_saved_address(self.case,{'houseSelectedFromList':True},p)
  self.assertRaises(RuntimeError,audit.validate_saved_address,self.case,{},p)
 def test_postal_path_keeps_original_id_guards(self):
  p=copy.deepcopy(self.place);p['addressOrigin']='postal'
  self.assertRaises(RuntimeError,audit.validate_saved_address,self.case,self.result,p)
  p['addressSelection']['street']['id']='postal-1';audit.validate_saved_address(self.case,self.result,p)
 def test_new_signed_binary_does_not_change_frozen_street_identity(self):
  self.assertTrue(audit.street_matches('вулиця Тараса Шевченка · довідник оператора','Тараса Шевченка вулиця'))
  self.assertFalse(audit.street_matches('провулок Тараса Шевченка','вулиця Тараса Шевченка'))
if __name__=='__main__':unittest.main()
