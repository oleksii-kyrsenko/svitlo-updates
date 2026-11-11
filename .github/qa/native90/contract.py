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

def candidate_url(candidate):
 from urllib.parse import urlsplit
 url=candidate.get('apkUrl','https://raw.githubusercontent.com/oleksii-kyrsenko/svitlo-updates/feature/capital-coverage-90/candidate/'+candidate['fileName'])
 parsed=urlsplit(url);parts=parsed.path.split('/')[1:]
 if (parsed.scheme!='https' or parsed.netloc!='raw.githubusercontent.com' or
     parts[:2]!=['oleksii-kyrsenko','svitlo-updates'] or len(parts)<5 or
     parts[-2:]!=['candidate',candidate['fileName']] or parsed.query or parsed.fragment or
     any(part in ['.','..'] or not re.fullmatch(r'[A-Za-z0-9_.-]+',part) for part in parts)):
  raise ValueError('Candidate URL must bind the pinned public QA file')
 return url

BASELINE = {'packageName':'ua.svitlo.app.testing','version':'0.1.53','versionCode':89,
            'size':82248242,'sha256':'f2309b850e9b953e6d94cbf9b63c8a6e4d6b01af570d512155a15401ee15017d',
            'apkUrl':'https://github.com/oleksii-kyrsenko/svitlo-updates/releases/download/android-test-89/svitlo-test-89.apk'}

def validate_metadata(candidate,baseline):
 if baseline!=BASELINE:raise ValueError('Baseline must be the published, user-confirmed build89')
 if candidate.get('packageName')!=BASELINE['packageName'] or candidate.get('versionCode')!=90 or candidate.get('version')!='0.1.54':raise ValueError('Expected next candidate0.1.54/build90')
 if candidate.get('publishedToUpdateChannel') is not False:raise ValueError('Acceptance candidate must remain unpublished')
 if not re.fullmatch(r'[a-f0-9]{64}',candidate.get('sha256','')) or candidate['sha256']==BASELINE['sha256']:raise ValueError('New candidate SHA256 must bind different APK bytes')
 if not isinstance(candidate.get('size'),int) or isinstance(candidate['size'],bool) or not 1_000_000<=candidate['size']<=150_000_000:raise ValueError('Candidate APK size missing')
 if not re.fullmatch(r'[a-f0-9]{40}',candidate.get('sourceCommit','')):raise ValueError('Clean source commit pin required')
 if not re.fullmatch(r'svitlo-candidate-90(?:-[a-z0-9]+)*\.apk',candidate.get('fileName','')):raise ValueError('Candidate file must bind build90')
 candidate_url(candidate)
 return candidate

def prepare():
 root=pathlib.Path('.github/qa/native90');out=pathlib.Path('apk-diagnostics');out.mkdir(exist_ok=True)
 spec=importlib.util.spec_from_file_location('audit_contract','.github/qa/audit-contract.py');c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
 if not (root/'meta.json').is_file():raise ValueError('Candidate90 meta.json is absent: seal the real native APK before dispatch; placeholders are forbidden')
 candidate=json.loads((root/'meta.json').read_text());baseline=json.loads((root/'baseline-89.json').read_text());validate_metadata(candidate,baseline)
 if not re.fullmatch(r'svitlo-candidate-[0-9]+(?:-[a-z0-9]+)*\.apk',candidate['fileName']):raise ValueError('Invalid pinned candidate file name')
 candidate['apkUrl']=candidate_url(candidate)
 for m,path,label in [(candidate,'candidate/'+candidate['fileName'],'candidate'),(baseline,'previous.apk','baseline')]:
  pathlib.Path(path).parent.mkdir(parents=True,exist_ok=True)
  if not pathlib.Path(path).exists():download(m,path)
  assert_bytes(path,m)
  report=c.verify_apk(path,{'apkSize':m['size'],'apkSha256':m['sha256'],'versionCode':m['versionCode'],'version':m['version']},diagnostics=out/(label+'-signature'))
  (out/(label+'-verification.json')).write_text(json.dumps(report,indent=2)+'\n')
 helper=root/'qa-input-helper.apk'
 if digest(helper)!='8994981c535eb14413f9169940f964563fba32124db256c9f96c0073b704befa':raise ValueError('QA input helper hash differs')
 print('Exact baseline89 and candidate90 binary hashes, package versions and pinned certificate verified')

if __name__=='__main__':prepare()
