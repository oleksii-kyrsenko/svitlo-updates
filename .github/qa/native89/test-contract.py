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
