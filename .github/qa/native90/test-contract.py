import importlib.util,unittest,tempfile,pathlib,hashlib,json
s=importlib.util.spec_from_file_location('native',pathlib.Path(__file__).with_name('contract.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class NativeContract(unittest.TestCase):
 def test_installed_hash_and_version_are_required(self):
  with tempfile.TemporaryDirectory() as d:
   data=b'actual installed source APK';meta={'packageName':'ua.svitlo.app.testing','versionCode':89,'size':len(data),'sha256':hashlib.sha256(data).hexdigest()}
   def adb(*args):
    if args[:3]==('shell','pm','path'):return 'package:/data/app/pkg/base.apk\n'
    if args[0]=='pull':pathlib.Path(args[2]).write_bytes(data);return ''
    return 'versionCode=89 minSdk=24'
   p=pathlib.Path(d)/'proof.json';m.verify_installed(adb,meta,p);self.assertTrue(json.loads(p.read_text())['verified']);self.assertFalse(p.with_suffix('.apk').exists())
   with self.assertRaises(ValueError):m.verify_installed(adb,{**meta,'sha256':'0'*64},p)
   with self.assertRaises(ValueError):m.verify_installed(adb,{**meta,'versionCode':88},p)
 def test_candidate_url_binds_reviewed_branch_and_exact_public_file(self):
  candidate={'fileName':'svitlo-candidate-90-control.apk'}
  good='https://raw.githubusercontent.com/oleksii-kyrsenko/svitlo-updates/feature/capital-coverage-90/candidate/'+candidate['fileName']
  self.assertEqual(m.candidate_url({**candidate,'apkUrl':good}),good)
  self.assertIn('/feature/capital-coverage-90/',m.candidate_url(candidate))
  for bad in [good.replace('/oleksii-kyrsenko/','/other/'),good+'?v=1',good+'#fragment',good.replace('/feature/','/feature/../'),good.replace('/feature/','/feature/%2e%2e/'),good.replace(candidate['fileName'],'wrong.apk'),good.replace('https://','http://'),good.replace('raw.githubusercontent.com','raw.githubusercontent.com:443')]:
   with self.subTest(url=bad),self.assertRaises(ValueError):m.candidate_url({**candidate,'apkUrl':bad})
 def test_published89_is_the_only_upgrade_baseline_and_candidate90_must_be_new_real_metadata(self):
  candidate={'packageName':m.BASELINE['packageName'],'version':'0.1.54','versionCode':90,'size':1000001,'sha256':hashlib.sha256(b'synthetic candidate metadata control').hexdigest(),'sourceCommit':'b'*40,'fileName':'svitlo-candidate-90-control.apk','publishedToUpdateChannel':False,'apkUrl':'https://raw.githubusercontent.com/oleksii-kyrsenko/svitlo-updates/feature/capital-coverage-90/candidate/svitlo-candidate-90-control.apk'}
  self.assertIs(m.validate_metadata(candidate,m.BASELINE.copy()),candidate)
  for patch in [{'versionCode':89},{'version':'0.1.53'},{'sha256':m.BASELINE['sha256']},{'size':True},{'sourceCommit':'main'},{'fileName':'svitlo-candidate-89.apk'},{'publishedToUpdateChannel':True},{'apkUrl':'https://example.org/candidate90.apk'}]:
   with self.subTest(patch=patch),self.assertRaises(ValueError):m.validate_metadata({**candidate,**patch},m.BASELINE)
  for patch in [{'versionCode':88},{'version':'0.1.52'},{'sha256':'0'*64},{'apkUrl':m.BASELINE['apkUrl'].replace('89','88')}]:
   with self.subTest(baseline=patch),self.assertRaises(ValueError):m.validate_metadata(candidate,{**m.BASELINE,**patch})
 def test_ipv4_and_ipv6_isolation_must_both_be_present(self):
  with tempfile.TemporaryDirectory() as d:
   calls=[]
   def adb(*args):
    calls.append(args)
    if args[:3]==('shell','stat','-c'):return '10123'
    return '-A OUTPUT -m owner --uid-owner 10123 -j DROP'
   m.block_app_network(adb,pathlib.Path(d)/'proof.json')
   self.assertEqual([a[1] for a in calls if len(a)>2 and a[2]=='-I'],['iptables','ip6tables'])
   with self.assertRaises(ValueError):m.block_app_network(lambda *a:'10123' if a[1]=='stat' else '',pathlib.Path(d)/'failure.json')
 def test_invalid_uid_never_reaches_shell_rule(self):
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaises(ValueError):m.block_app_network(lambda *a:'0; injected',pathlib.Path(d)/'proof.json')
if __name__=='__main__':unittest.main()
