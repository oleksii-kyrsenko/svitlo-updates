"""Public external QA contract. Never imports application implementation."""
import argparse, hashlib, json, os, pathlib, re, subprocess
from urllib.parse import urlsplit

PACKAGE = 'ua.svitlo.app.testing'
CERTIFICATE = 'fac61745dc0903786fb9ede62a962b399f7348f0bb6f899b8332667591033b9c'
FROZEN_SAMPLES = {
 '.github/qa/capital-baseline.json':'369aa30d4e4ec1f502b4d996f53b4555df953682ef4bf0449198d7c6eca97043',
 '.github/qa/capital-holdout.json':'15f9281c575adfcc0c7e795a3c8a45e60c3ef34569bb74fc082529d9144b751e',
}
DEFAULT = {'apkUrl':'https://github.com/oleksii-kyrsenko/svitlo-updates/releases/download/android-test-88/svitlo-test-88.apk',
 'apkSha256':'da4afbf50c9f1f4a563ef67fb56decdd0ba0e5ffde95f19789b97aff8e9ffc1a','apkSize':82323533,
 'versionCode':88,'version':'0.1.52','androidApi':35,'sample':'.github/qa/national-address-cases.json','chunkSize':5}

def sha256(path):
 h=hashlib.sha256()
 with pathlib.Path(path).open('rb') as f:
  for block in iter(lambda:f.read(1048576),b''):h.update(block)
 return h.hexdigest()

def sample_path(root,name):
 p=pathlib.Path(name)
 if p.is_absolute() or '..' in p.parts or p.suffix!='.json':raise ValueError('sample must be a contained repository JSON file')
 root=pathlib.Path(root).resolve();target=(root/p).resolve()
 if not target.is_relative_to(root) or not target.is_file():raise ValueError('sample missing or outside repository')
 return target

def contract(request,root='.'):
 c={**DEFAULT,**{k:v for k,v in request.items() if v is not None and v!=''}}
 url=urlsplit(c['apkUrl'])
 if url.scheme!='https' or not url.hostname or url.username or url.password or url.fragment:raise ValueError('APK requires public HTTPS URL')
 if not re.fullmatch(r'[a-f0-9]{64}',c['apkSha256']):raise ValueError('APK hash missing')
 for key in ['apkSize','versionCode','androidApi','chunkSize']:c[key]=int(c[key])
 if not 1<=c['apkSize']<=250000000 or not 1<=c['versionCode']<=2100000000 or c['androidApi'] not in [30,35,36] or not 1<=c['chunkSize']<=5:raise ValueError('invalid binary/API/chunk bounds')
 if not re.fullmatch(r'\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?',c['version']):raise ValueError('invalid version')
 path=sample_path(root,c['sample']);actual=sha256(path)
 if c.get('sampleSha256') and c['sampleSha256']!=actual:raise ValueError('sample hash differs from frozen request')
 c['sampleSha256']=actual;c['packageName']=PACKAGE;c['certificateSha256']=CERTIFICATE
 return c

def plan(request,root='.'):
 c=contract(request,root);targets=json.loads(sample_path(root,c['sample']).read_text())['cases']
 ids=[row['id'] for row in targets]
 if len(ids)!=len(set(ids)):raise ValueError('duplicate frozen case identifiers')
 regions=request.get('regions')
 if not isinstance(regions,list) or not regions or len(regions)!=len(set(regions)) or any(not re.fullmatch(r'UA-\d\d',r) for r in regions):raise ValueError('invalid region request')
 if any(r not in {v['regionId'] for v in targets} for r in regions):raise ValueError('requested region absent from sample')
 selected=request.get('caseIds',[]);limit=int(request.get('limit',5))
 if not isinstance(selected,list) or len(selected)!=len(set(selected)) or any(case not in {v['id'] for v in targets if v['regionId'] in regions} for case in selected):raise ValueError('invalid explicit case request')
 if not 1<=limit<=20:raise ValueError('limit must be1..20')
 matrix=[]
 for region in regions:
  cases=[v['id'] for v in targets if v['regionId']==region and (not selected or v['id'] in selected)][:limit]
  if not cases:raise ValueError('empty regional request')
  for start in range(0,len(cases),c['chunkSize']):matrix.append({'region':region,'chunk':start//c['chunkSize']+1,'caseIds':','.join(cases[start:start+c['chunkSize']])})
 return c,{'include':matrix}

def tools(sdk=None):
 root=pathlib.Path(sdk or os.environ.get('ANDROID_HOME') or os.environ.get('ANDROID_SDK_ROOT','/opt/android-sdk'))
 candidates=sorted((root/'build-tools').glob('*'),key=lambda p:tuple(int(v) for v in re.findall(r'\d+',p.name)),reverse=True)
 # Use the same stable build-tools as the native builder when installed.
 # Preview/latest SDK output is not the verifier contract for this candidate.
 candidates.sort(key=lambda p:p.name!='36.0.0')
 found=next((p for p in candidates if (p/'aapt').is_file() and (p/'apksigner').is_file()),None)
 if not found:raise ValueError('Android build tools unavailable')
 return found

def signing_certificate(signature):
 # apksigner formats vary across SDKs (numbered signer, SDK range, uppercase
 # or colon-delimited digest). Parse only signer certificates, never public-key
 # or SourceStamp fingerprints, while retaining the exact single-signer pin.
 counts=re.findall(r'^\s*Number of signers:\s*(\d+)\s*$',signature,re.M|re.I)
 if counts and counts!=['1']:raise ValueError('unexpected additional APK signer')
 headers=re.findall(r'^\s*Signer[^\r\n]*\bcertificate\s+SHA-256\s+digest:',signature,re.M|re.I)
 if len(headers)!=1:raise ValueError('expected exactly one APK signer certificate digest')
 matches=re.findall(r'^\s*(Signer(?:\s+#\d+)?(?:\s*\([^\r\n)]*\))?)\s+certificate\s+SHA-256\s+digest:\s*([a-f0-9: \t]+)\s*$',signature,re.M|re.I)
 if len(matches)!=1:raise ValueError('expected exactly one APK signer certificate digest')
 label,value=matches[0];number=re.search(r'#(\d+)',label)
 if number and number[1]!='1':raise ValueError('unexpected APK signer identity')
 actual=re.sub(r'[: \t]','',value).lower()
 if not re.fullmatch(r'[a-f0-9]{64}',actual) or actual!=CERTIFICATE:raise ValueError('APK signing certificate differs')
 return actual

def verify_apk(path,c,sdk=None,runner=subprocess.check_output,diagnostics=None):
 path=pathlib.Path(path)
 if path.stat().st_size!=c['apkSize'] or sha256(path)!=c['apkSha256']:raise ValueError('APK bytes differ from requested binary')
 bin=tools(sdk);proof=pathlib.Path(diagnostics) if diagnostics else None
 if proof:
  proof.mkdir(parents=True,exist_ok=True)
  (proof/'verification-tools.json').write_text(json.dumps({'buildTools':bin.name,'directory':str(bin),'apkSha256':c['apkSha256'],'expectedCertificateSha256':CERTIFICATE},indent=2)+'\n')
 try:signature=runner([str(bin/'apksigner'),'verify','--verbose','--print-certs',str(path)],text=True,stderr=subprocess.STDOUT)
 except subprocess.CalledProcessError as error:
  if proof:(proof/'signature-output.txt').write_text(error.output.decode(errors='replace') if isinstance(error.output,bytes) else str(error.output or ''))
  raise
 if proof:(proof/'signature-output.txt').write_text(signature)
 actual=signing_certificate(signature)
 badging=runner([str(bin/'aapt'),'dump','badging',str(path)],text=True,stderr=subprocess.STDOUT)
 if proof:(proof/'apk-badging.txt').write_text(badging)
 package=re.search(r"^package: name='([^']+)' versionCode='(\d+)' versionName='([^']+)'",badging,re.M)
 if not package or package.groups()!=(PACKAGE,str(c['versionCode']),c['version']):raise ValueError('APK package/version differs')
 return {'apkSha256':c['apkSha256'],'apkSize':c['apkSize'],'versionCode':c['versionCode'],'version':c['version'],'packageName':PACKAGE,'certificateSha256':actual,'signatureVerified':True,'buildTools':bin.name}

def dispatch_request(request,environ=None):
 request={**request};environ=os.environ if environ is None else environ
 # A different frozen sample has its own digest. Retaining the committed
 # baseline digest makes a legitimate holdout dispatch fail before any case;
 # dropping the digest would silently permit replacing the frozen sample.
 sample=environ.get('INPUT_SAMPLE')
 if sample and sample!=request.get('sample'):
  if sample not in FROZEN_SAMPLES:raise ValueError('sample override must select a pinned frozen capital sample')
  request['sampleSha256']=FROZEN_SAMPLES[sample]
 fields={'INPUT_REGIONS':'regions','INPUT_LIMIT':'limit','INPUT_APK_URL':'apkUrl','INPUT_APK_SHA256':'apkSha256','INPUT_APK_SIZE':'apkSize','INPUT_VERSION_CODE':'versionCode','INPUT_VERSION':'version','INPUT_API':'androidApi','INPUT_SAMPLE':'sample','INPUT_CHUNK_SIZE':'chunkSize'}
 for env,key in fields.items():
  if environ.get(env):request[key]=json.loads(environ[env]) if key=='regions' else environ[env]
 if environ.get('INPUT_REGIONS'):request['caseIds']=[]
 if environ.get('INPUT_CASE_IDS'):request['caseIds']=json.loads(environ['INPUT_CASE_IDS'])
 return request

def main():
 p=argparse.ArgumentParser();p.add_argument('action',choices=['plan','verify']);p.add_argument('--request',default='.github/qa/national-audit-request.json');p.add_argument('--apk');p.add_argument('--output');a=p.parse_args()
 request=json.loads(pathlib.Path(a.request).read_text()) if pathlib.Path(a.request).is_file() else {}
 if a.action=='plan':
  request=dispatch_request(request)
  c,m=plan(request)
  if a.output:pathlib.Path(a.output).write_text(json.dumps(c,ensure_ascii=False,indent=2)+'\n')
  if os.environ.get('GITHUB_OUTPUT'):
   with open(os.environ['GITHUB_OUTPUT'],'a') as f:f.write('contract='+json.dumps(c,ensure_ascii=False)+'\nmatrix='+json.dumps(m)+'\n')
  print(json.dumps({'contract':c,'matrix':m},ensure_ascii=False))
 else:
  c=contract(request);report=verify_apk(a.apk,c,diagnostics=pathlib.Path(a.output).parent if a.output else None)
  if a.output:pathlib.Path(a.output).write_text(json.dumps(report,indent=2)+'\n')
  print(json.dumps(report))
if __name__=='__main__':main()
