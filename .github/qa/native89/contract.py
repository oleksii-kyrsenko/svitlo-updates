"""External native retention acceptance; never used to assign or count a queue."""
import hashlib,json,pathlib,re,importlib.util,urllib.request

def digest(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for block in iter(lambda:f.read(1048576),b''):h.update(block)
 return h.hexdigest()

def assert_bytes(path,meta):
 if pathlib.Path(path).stat().st_size!=meta['size'] or digest(path)!=meta['sha256']:raise ValueError('Pinned APK bytes differ')

def download(meta,path):
 with urllib.request.urlopen(meta['apkUrl'],timeout=150) as r,open(path,'wb') as f:
  size=0
  for block in iter(lambda:r.read(1048576),b''):
   size+=len(block)
   if size>meta['size']:raise ValueError('APK exceeds pinned size')
   f.write(block)
 assert_bytes(path,meta)

def verify_installed(adb,meta,proof):
 paths=adb('shell','pm','path',meta['packageName']).splitlines()
 if len(paths)!=1 or not paths[0].startswith('package:') or not paths[0].endswith('/base.apk'):raise ValueError('Expected exactly one installed base APK')
 target=pathlib.Path(proof).with_suffix('.apk')
 try:
  adb('pull',paths[0][8:].strip(),str(target));assert_bytes(target,meta)
 finally:target.unlink(missing_ok=True)
 state=adb('shell','dumpsys','package',meta['packageName'])
 if not re.search(r'\bversionCode='+str(meta['versionCode'])+r'\b',state):raise ValueError('Installed versionCode differs')
 pathlib.Path(proof).write_text(json.dumps({'verified':True,'packageName':meta['packageName'],'versionCode':meta['versionCode'],'apkSha256':meta['sha256'],'size':meta['size']},indent=2)+'\n')

def block_app_network(adb,proof):
 uid=adb('shell','stat','-c','%u','/data/data/ua.svitlo.app.testing').strip()
 if not re.fullmatch(r'[1-9]\d{3,7}',uid):raise ValueError('Invalid application UID')
 rules={}
 for table in ['iptables','ip6tables']:
  args=['OUTPUT','-m','owner','--uid-owner',uid,'-j','DROP']
  adb('shell',table,'-I',*args)
  listing=adb('shell',table,'-S','OUTPUT')
  if not any('--uid-owner '+uid in line and '-j DROP' in line for line in listing.splitlines()):raise ValueError('Application offline rule missing')
  rules[table]=listing
 pathlib.Path(proof).write_text(json.dumps({'scope':'test emulator only; all application UID IPv4/IPv6 output blocked','uid':uid,'rules':rules},indent=2)+'\n')

def prepare():
 root=pathlib.Path('.github/qa/native89');out=pathlib.Path('apk-diagnostics');out.mkdir(exist_ok=True)
 spec=importlib.util.spec_from_file_location('audit_contract','.github/qa/audit-contract.py');c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
 candidate=json.loads((root/'meta.json').read_text());baseline=json.loads((root/'baseline-88.json').read_text())
 if not re.fullmatch(r'svitlo-candidate-[0-9]+(?:-[a-z0-9]+)*\.apk',candidate['fileName']):raise ValueError('Invalid pinned candidate file name')
 candidate['apkUrl']='https://raw.githubusercontent.com/oleksii-kyrsenko/svitlo-updates/feature/capital-coverage-90/candidate/'+candidate['fileName']
 for m,path,label in [(candidate,'candidate/'+candidate['fileName'],'candidate'),(baseline,'previous.apk','baseline')]:
  if not pathlib.Path(path).exists():download(m,path)
  assert_bytes(path,m)
  report=c.verify_apk(path,{'apkSize':m['size'],'apkSha256':m['sha256'],'versionCode':m['versionCode'],'version':m['version']},diagnostics=out/(label+'-signature'))
  (out/(label+'-verification.json')).write_text(json.dumps(report,indent=2)+'\n')
 helper=root/'qa-input-helper.apk'
 if digest(helper)!='8994981c535eb14413f9169940f964563fba32124db256c9f96c0073b704befa':raise ValueError('QA input helper hash differs')
 print('Exact baseline88 and candidate89 binary hashes, package versions and pinned certificate verified')

if __name__=='__main__':prepare()
