"""External UI acceptance for dated third-party hints; never a coverage result.

All address/queue choices use ordinary app controls. Expected source facts are
read independently from an immutable public source; Android SQLite is read only.
"""
import argparse,datetime,hashlib,importlib.util,json,os,pathlib,re,subprocess,time,traceback,unicodedata,urllib.parse,urllib.request,xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo
HERE=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('national_audit',HERE/'national-address-audit.py')
national=importlib.util.module_from_spec(spec);spec.loader.exec_module(national)
MANIFEST_URL='https://raw.githubusercontent.com/oleksii-kyrsenko/svitlo-updates/main/public-evidence/manifest.json'
DAY=86400000
SAMPLES={'.github/qa/capital-baseline.json':'369aa30d4e4ec1f502b4d996f53b4555df953682ef4bf0449198d7c6eca97043','.github/qa/capital-holdout.json':'15f9281c575adfcc0c7e795a3c8a45e60c3ef34569bb74fc082529d9144b751e'}
WARNING='Це датовані відомості зі сторонньої бази.'
REVIEWED_SOURCE={'repository':'Elvis129/prosvitlo-addresses-db','commit':'abb932c0a46474864c67ecd80bfd7e117500785c','path':'addresses_pl_v1.json','sha256':'ccf8490374eff3eab4c30f933406133492d1b3067e2bb0adec0f92926b76487a','publishedCommit':'0d5a090c80c62e765fcaf44a1d9e13a7add80168','publishedAt':1792244685000}
spec=importlib.util.spec_from_file_location('historical_screen',HERE/'native90/historical-screen.py');historical_screen=importlib.util.module_from_spec(spec);spec.loader.exec_module(historical_screen)

def digest(raw):return hashlib.sha256(raw).hexdigest()
def compact(value):return json.dumps(value,ensure_ascii=False,separators=(',',':'))
def write_json(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def unique_object(pairs):
 result={}
 for key,value in pairs:
  if key in result:raise ValueError('Duplicate source JSON key')
  result[key]=value
 return result

def bounded_read(url,maximum):
 request=urllib.request.Request(url,headers={'Accept':'application/json','User-Agent':'KolySvitloHistoricalUIQA/1.0'})
 with urllib.request.urlopen(request,timeout=45) as response:
  if response.status!=200 or response.url!=url:raise ValueError('Source status/redirect differs from pinned URL')
  raw=response.read(maximum+1)
 if len(raw)>maximum:raise ValueError('Source exceeds QA size bound')
 return raw

def house_key(value):return re.sub(r'\s+','',unicodedata.normalize('NFKC',value).lower()).replace('’',"'").replace('ʼ',"'")
def katottg_key(value):
 if not isinstance(value,str) or not re.fullmatch(r'(?:UA)?[0-9]{17}',value):raise ValueError('Exact postal KATOTTG identity required')
 return value.removeprefix('UA')
def road_key(value):
 kind,name=national.street_identity(value)
 # Source spellings may move the road type, but cannot change words or type.
 return kind,tuple(sorted(unicodedata.normalize('NFKC',name).split()))

def pointer_get(data,pointer):
 if not isinstance(pointer,str) or not pointer.startswith('/'):raise ValueError('JSON pointer required')
 current=data
 for value in pointer[1:].split('/'):
  if re.search(r'~(?![01])',value):raise ValueError('Invalid JSON pointer escape')
  current=current[value.replace('~1','/').replace('~0','~')]
 return current

def validate_record(record,now):
 if (record.get('recordVersion'),record.get('evidenceType'),record.get('scope'),record.get('method'),record.get('historical'),record.get('requiresConfirmation'))!=(5,'historical-directory','house','direct',True,True):raise ValueError('Explicit historical house proposal required')
 if not re.fullmatch(r'[a-f0-9]{16,100}',record.get('id','')) or not re.fullmatch(r'UA\d{17}',record.get('katottg','')):raise ValueError('Historical record/geography identity missing')
 published=record.get('publishedAt');fetched=record.get('fetchedAt');expires=record.get('expiresAt')
 if any(isinstance(v,bool) or not isinstance(v,(int,float)) for v in [published,fetched,expires]):raise ValueError('Source/observation/expiry dates required')
 if not 7*DAY<now-published<=180*DAY or not 0<=now-fetched<=36*3600000 or not now<expires<=min(fetched+7*DAY,published+180*DAY):raise ValueError('Acceptance requires a genuinely old, currently eligible hint')
 snapshot=record.get('sourceSnapshot') or {};context=record.get('sourceContext') or {}
 if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',snapshot.get('repository','')) or any(not re.fullmatch(r'[a-f0-9]{40}',snapshot.get(k,'')) for k in ['commit','publishedCommit']) or not re.fullmatch(r'[a-f0-9]{64}',snapshot.get('sha256','')):raise ValueError('Immutable source pins required')
 path=snapshot.get('path','')
 if not re.fullmatch(r'[A-Za-z0-9_./-]+',path) or any(part in ('','.','..') for part in path.split('/')):raise ValueError('Contained immutable source path required')
 expected='https://raw.githubusercontent.com/'+snapshot['repository']+'/'+snapshot['commit']+'/'+path
 if record.get('sourceUrl')!=expected or context.get('basisUrl')!=expected or snapshot.get('publishedAt')!=published:raise ValueError('Source URL or original publication changed')
 if context.get('verified') is not True or any(context.get(k)!=record.get(k) for k in ['settlement','community','regionId']):raise ValueError('Source geography context differs')
 escaped=record['street'].replace('~','~0').replace('/','~1')
 if snapshot.get('jsonPointer')!=context.get('jsonPointer','')+'/streets/'+escaped:raise ValueError('Street pointer differs')
 houses=record.get('houses')
 if not isinstance(houses,list) or not 1<=len(houses)<=100 or len(set(map(house_key,houses)))!=len(houses) or any(not isinstance(h,str) or not re.fullmatch(r'\d{1,4}[а-яіїєґa-z]?(?:/\d{1,4}[а-яіїєґa-z]?)?',unicodedata.normalize('NFKC',h),re.I) for h in houses):raise ValueError('Only unique literal houses are eligible')
 if any(record.get(k) for k in ['adapter','validity','sources','reasoning','houseRanges','excludedHouses']):raise ValueError('Historical exact-house claims cannot infer scope or validity')
 if not re.fullmatch(r'[1-6]\.[12]',record.get('queue','')):raise ValueError('Literal original GPV subgroup required')
 if any(not isinstance(value,str) or len(value.encode('utf-8'))>maximum for value,maximum in [(record.get('quote'),2500),(context.get('quote'),1000)]):raise ValueError('Lossless source quotes exceed client bounds')
 quote=json.loads(record['quote'],object_pairs_hook=unique_object);location=json.loads(context['quote'],object_pairs_hook=unique_object)
 if quote!={record['street']:{h:[record['queue']] for h in houses}} or location!={"name":record['settlement'],"hromada":record['community'],"katottg":record['katottg']}:raise ValueError('Lossless quote/context differs from explicit claims')
 return record

def verify_source_projection(record,raw):
 if len(raw)>15000000 or digest(raw)!=record['sourceSnapshot']['sha256']:raise ValueError('Raw immutable snapshot differs from SHA256')
 source=json.loads(raw,object_pairs_hook=unique_object);context=pointer_get(source,record['sourceContext']['jsonPointer']);street=pointer_get(source,record['sourceSnapshot']['jsonPointer'])
 if {k:context.get(k) for k in ['name','hromada','katottg']}!=json.loads(record['sourceContext']['quote']):raise ValueError('Original source locality differs')
 fragment=json.loads(record['quote'])[record['street']]
 if any(street.get(h)!=queue for h,queue in fragment.items()):raise ValueError('Original source exact-house GPV differs')
 return {'rawSha256':digest(raw),'rawBytes':len(raw),'exactSourceProjectionVerified':True,'sourcePublishedAt':record['publishedAt'],'sourceSnapshot':record['sourceSnapshot']}

def require_reviewed_source(record):
 if any(record['sourceSnapshot'].get(k)!=value for k,value in REVIEWED_SOURCE.items()):raise ValueError('Historical UI acceptance requires the independently reviewed October17 GPV source pin')

def verify_publication(record,raw):
 body=json.loads(raw,object_pairs_hook=unique_object);snapshot=record['sourceSnapshot']
 if body.get('sha')!=snapshot['publishedCommit']:raise ValueError('Publication commit identity differs')
 date=body.get('commit',{}).get('committer',{}).get('date')
 if not isinstance(date,str) or int(datetime.datetime.fromisoformat(date.replace('Z','+00:00')).timestamp()*1000)!=record['publishedAt']:raise ValueError('Original publication commit date differs')
 # Verify this commit actually touched the pinned file. Later repository-wide
 # version timestamps cannot provide publication evidence for these GPV facts.
 if not any(file.get('filename')==snapshot['path'] and file.get('status') in ['added','modified','renamed'] for file in body.get('files',[])):raise ValueError('Publication commit did not change this source file')
 return {'publishedCommit':body['sha'],'publishedAt':record['publishedAt'],'commitSourceVerified':True}

def select_case(records,samples,now,case_id=None):
 choices=[];eligible=[]
 for record in records:
  try:validate_record(record,now)
  except (ValueError,KeyError,TypeError):continue
  eligible.append(record)
 for sample,data in samples.items():
  for case in data['cases']:
   if case_id and case['id']!=case_id:continue
   for record in eligible:
    if record['regionId']!=case['regionId'] or national.norm(record['settlement'])!=national.norm(case['city']):continue
    if not any(road_key(record['street'])==road_key(v) for v in national.case_street_variants(case)):continue
    if not any(house_key(case['exactHouse'])==house_key(h) for h in record['houses']):continue
    choices.append((sample,case,record))
 # One frozen physical address must have one historical claim before this
 # positive acceptance scenario can be selected. Conflicts belong to negatives.
 by_case={}
 for sample,case,record in choices:by_case.setdefault(case['id'],[]).append((sample,case,record))
 for case in sorted(by_case):
  values=by_case[case]
  if len(values)==1:return values[0]
 raise ValueError('No unique dated exact-house hint matches the frozen samples; nothing is substituted')

def plan(args):
 now=int(time.time()*1000);out=args.out;out.mkdir(parents=True,exist_ok=True)
 raw=bounded_read(MANIFEST_URL,2000000);manifest=json.loads(raw,object_pairs_hook=unique_object)
 if manifest.get('schemaVersion') not in [1,2,3] or manifest.get('enabled') is not True or not isinstance(manifest.get('records'),list) or len(manifest['records'])>10000 or not 0<=now-manifest.get('generatedAt',0)<=36*3600000:raise ValueError('Public hint manifest unavailable/stale')
 samples={}
 for path,pin in SAMPLES.items():
  data=pathlib.Path(path).read_bytes()
  if digest(data)!=pin:raise ValueError('Frozen geographic sample changed')
  samples[path]=json.loads(data)
 sample,case,record=select_case(manifest['records'],samples,now,args.case_id)
 require_reviewed_source(record)
 source=bounded_read(record['sourceUrl'],15000000);proof=verify_source_projection(record,source)
 url='https://api.github.com/repos/'+record['sourceSnapshot']['repository']+'/commits/'+record['sourceSnapshot']['publishedCommit']
 publication=bounded_read(url,2000000);proof.update(verify_publication(record,publication),publicationUrl=url,publicationResponseSha256=digest(publication))
 request={'apkUrl':args.apk_url,'apkSha256':args.apk_sha256,'apkSize':args.apk_size,'versionCode':args.version_code,'version':args.version,'sample':sample,'sampleSha256':SAMPLES[sample],'androidApi':35}
 binary=national.audit_contract.contract(request)
 contract={'schemaVersion':1,'kind':'dated-historical-hint-ui-acceptance-not-coverage','plannedAt':now,'binary':binary,'case':case,'record':record,'manifestUrl':MANIFEST_URL,'manifestSha256':digest(raw),'sourceProof':proof,'noAddressStorageSeeding':True,'noQueueEntry':True,'officialAutomaticCoverageContribution':0}
 (out/'public-manifest.json').write_bytes(raw);(out/'source-snapshot.json').write_bytes(source);(out/'publication-commit.json').write_bytes(publication);write_json(out/'plan.json',contract)
 pin=digest((out/'plan.json').read_bytes())
 if os.environ.get('GITHUB_OUTPUT'):
  with open(os.environ['GITHUB_OUTPUT'],'a') as f:f.write('plan_sha256='+pin+'\n')
 print(compact({'caseId':case['id'],'sourceRecordId':record['id'],'sourcePublishedAt':record['publishedAt'],'sourceSha256':record['sourceSnapshot']['sha256'],'planSha256':pin,'officialAutomaticCoverageContribution':0}))


def active_place(state):
 place=next((p for p in state.get('places',[]) if p.get('id')==state.get('activePlaceId')),None)
 if not place:raise ValueError('App did not persist an active address')
 return place

def same_address(case,initial,place):
 if place.get('id')!=initial.get('id') or place.get('address')!=initial.get('address') or place.get('addressParts')!=initial.get('addressParts'):raise ValueError('Active physical address or UUID changed')
 if place.get('operatorId')!=initial.get('operatorId') or place.get('regionId')!=case['regionId']:raise ValueError('Address operator/geography changed')

def expected_source_address(record,house):
 matches=[literal for literal in record['houses'] if house_key(literal)==house_key(house)]
 if len(matches)!=1:raise ValueError('Frozen house does not have exactly one literal source member')
 return record['settlement']+', '+record['street']+', будинок '+matches[0]

def verify_pending(place,record,source_address):
 if place.get('queueConfirmed') or place.get('queue') or place.get('queueOrigin') in ['official','manual']:raise ValueError('Historical hint was assigned before an explicit user choice')
 candidate=next((c for c in place.get('queuePublicCandidates',[]) if c.get('id')==record['id']),None)
 if not candidate or candidate.get('origin')!='public' or candidate.get('publicHistorical') is not True or candidate.get('publicPublishedAt')!=record['publishedAt'] or candidate.get('publicSnapshot')!=record['sourceSnapshot'] or candidate.get('queue')!=record['queue']:raise ValueError('Pending candidate differs from the original historical evidence')
 if candidate.get('publicAddressLabel')!=source_address:raise ValueError('Pending candidate source address differs from the exact frozen house')
 if candidate.get('publicObservedAt')!=record['fetchedAt'] or candidate.get('publicExpiresAt')!=record['expiresAt'] or candidate.get('sourceUrl')!=record['sourceUrl']:raise ValueError('Pending observation/eligibility/provenance changed')
 return candidate

def verify_confirmed(place,record,earliest,initial,confirmation=None):
 same_address({'regionId':record['regionId']},initial,place)
 if not(place.get('queueConfirmed') is True and place.get('queueOrigin')=='public' and place.get('queue')==record['queue'] and place.get('queuePublicHistorical') is True and place.get('queueEvidence')=='public-historical-directory'):raise ValueError('User choice was lost or promoted to official/manual')
 if place.get('queuePublicPublishedAt')!=record['publishedAt'] or place.get('queuePublicSnapshot')!=record['sourceSnapshot'] or place.get('queueSource')!=record['sourceUrl']:raise ValueError('Saved original date/provenance changed')
 if place.get('queuePublicObservedAt')!=record['fetchedAt'] or place.get('queuePublicExpiresAt')!=record['expiresAt']:raise ValueError('Saved observation date or eligibility was silently renewed')
 accepted=place.get('queueUserConfirmedAt')
 if not isinstance(accepted,(int,float)) or isinstance(accepted,bool) or accepted<earliest or accepted>int(time.time()*1000)+5000:raise ValueError('Explicit confirmation timestamp missing')
 if place.get('reminders',{}).get('enabled'):raise ValueError('Selecting a historical hint enabled reminders automatically')
 if place.get('queuePublicAddressLabel')!=expected_source_address(record,initial['addressParts']['house']):raise ValueError('Saved literal source address changed')
 if confirmation is not None and accepted!=confirmation:raise ValueError('Refresh or restart replaced the explicit user confirmation timestamp')
 return place

class HistoricalAudit(national.Audit):
 def scan_notice(self,label,record,source_address,pending=False):
  for _ in range(16):self.scroll(False)
  date=datetime.datetime.fromtimestamp(record['publishedAt']/1000,ZoneInfo('Europe/Kyiv')).strftime('%d.%m.%Y')
  found=set();frames=[]
  for page in range(20):
   xml=self.source();scope='public-candidate-'+record['id'] if pending else 'public-queue-notice';binding=historical_screen.visible_notice(xml,scope,self.size['width'],self.size['height']);texts=binding['texts'];text=' '.join(texts)
   if WARNING in text and 'могли змінитися' in text:found.add('warning')
   if 'Дані джерела від '+date in text and 'не підтверджує їхню актуальність' in text:found.add('original-date')
   if 'Адреса в джерелі: '+source_address in texts:found.add('source-address')
   if pending and 'Ймовірна черга '+record['queue'] in text:found.add('probable-queue')
   if pending and 'не чинності даних' in text:found.add('eligibility-not-validity')
   if not pending and 'Це не підтвердження оператора.' in text:found.add('public-user-choice')
   if 'Переглянути джерело 1' in text or 'Переглянути публічне джерело' in text:found.add('source-link')
   if found and (page==0 or found-set().union(*(set(frame['found']) for frame in frames))):
    name=label+'-'+str(page).zfill(2);self.screenshot(name,xml);frames.append({'png':name+'.png','xml':name+'.xml','found':sorted(found),'visibleTexts':texts,'visibleBinding':binding})
   required={'warning','original-date','source-address','source-link'}|({'probable-queue','eligibility-not-validity'} if pending else {'public-user-choice'})
   if found>=required:return {'flags':sorted(found),'frames':frames,'originalSourceDate':date}
   self.scroll()
  raise RuntimeError('Visible historical notice incomplete: '+','.join(sorted(required-found)))
 def firewall(self,enable):
  dump=self.adb('shell','dumpsys','package',national.PKG);match=re.search(r'^\s*userId=(\d+)\s*$',dump,re.M)
  if not match:raise RuntimeError('Cannot identify this package UID for offline isolation')
  uid=match[1];rules=[]
  for tool in ['iptables','ip6tables']:
   if enable:self.adb('shell',tool,'-I','OUTPUT','1','-m','owner','--uid-owner',uid,'-j','DROP')
   self.adb('shell',tool,'-C','OUTPUT','-m','owner','--uid-owner',uid,'-j','DROP')
   rules.append({'tool':tool,'uid':int(uid),'verifiedDrop':True,'rules':self.adb('shell',tool,'-S','OUTPUT')})
  return {'packageName':national.PKG,'uid':int(uid),'verifiedIPv4AndIPv6':True,'rules':rules}


def run(args):
 plan_raw=args.plan.read_bytes()
 if digest(plan_raw)!=args.plan_sha256:raise ValueError('Selected source plan changed')
 plan=json.loads(plan_raw);record=plan['record'];validate_record(record,int(time.time()*1000))
 require_reviewed_source(record)
 folder=args.plan.parent
 if digest((folder/'public-manifest.json').read_bytes())!=plan['manifestSha256']:raise ValueError('Planned manifest bytes changed')
 verify_source_projection(record,(folder/'source-snapshot.json').read_bytes());verify_publication(record,(folder/'publication-commit.json').read_bytes())
 c=national.audit_contract.contract({**plan['binary'],'androidApi':args.api});args.out.mkdir(parents=True,exist_ok=True);write_json(args.out/'contract.json',c)
 national.audit_contract.verify_apk(args.apk,c,diagnostics=args.out)
 subprocess.run(['adb','root'],check=True,capture_output=True,timeout=45);subprocess.run(['adb','wait-for-device'],check=True,timeout=60)
 audit=None;result={'kind':plan['kind'],'startedAt':national.stamp(),'caseId':plan['case']['id'],'sourceRecordId':record['id'],'planSha256':args.plan_sha256,'sourceProof':plan['sourceProof'],'apkSha256':c['apkSha256'],'androidApi':args.api,'officialAutomaticCoverageContribution':0,'noAddressStorageSeeding':True,'noQueueEntry':True,'pass':False}
 try:
  audit=HistoricalAudit(args.apk,args.out,c)
  observed=audit.run_case(plan['case']);result['originalUIAttempt']=observed
  if observed.get('outcome')!='public_proposal_requires_confirmation':raise RuntimeError('App did not produce a pending public proposal: '+str(observed.get('outcome')))
  audit.case_dir=args.out/'historical-acceptance';audit.case_dir.mkdir(parents=True,exist_ok=True)
  state=audit.read_state();initial=active_place(state);national.validate_saved_address(plan['case'],observed,initial);source_address=expected_source_address(record,plan['case']['exactHouse']);candidate=verify_pending(initial,record,source_address)
  if katottg_key(initial.get('addressContext',{}).get('katottg'))!=katottg_key(record['katottg']):raise ValueError('Selected app city KATOTTG differs from the original source')
  write_json(audit.case_dir/'before-confirmation-state.json',state);result['beforeConfirmation']=audit.scan_notice('before-confirmation',record,source_address,True)
  audit.screenshot('before-explicit-choice');clicked_at=int(time.time()*1000);audit.tap('confirm-public-candidate-'+record['id'],scroll=True)
  time.sleep(2);state=audit.read_state();accepted=verify_confirmed(active_place(state),record,clicked_at,initial);write_json(audit.case_dir/'after-confirmation-state.json',state);result['afterConfirmation']=audit.scan_notice('after-confirmation',record,source_address)
  result['offlineBeforeRestart']=audit.firewall(True)
  audit.tap('schedule-refresh',scroll=True);audit.wait(lambda xml:'schedule-refresh-result' in xml,180);audit.screenshot('offline-refresh-result')
  state=audit.read_state();verify_confirmed(active_place(state),record,clicked_at,initial,accepted['queueUserConfirmedAt']);write_json(audit.case_dir/'after-offline-refresh-state.json',state)
  audit.adb('shell','am','force-stop',national.PKG);audit.adb('shell','am','start','-W','-n',national.PKG+'/.MainActivity');time.sleep(5)
  audit.wait(lambda xml:'current-address-name' in xml,55);state=audit.read_state();verify_confirmed(active_place(state),record,clicked_at,initial,accepted['queueUserConfirmedAt']);write_json(audit.case_dir/'after-offline-restart-state.json',state)
  result['offlineAfterRestart']=audit.firewall(False);result['afterOfflineRestart']=audit.scan_notice('after-offline-restart',record,source_address)
  result['pass']=True;result['confirmedQueueOrigin']='public';result['preservedActivePlaceId']=accepted['id'];result['sourcePublishedAt']=record['publishedAt'];result['confirmationAt']=accepted['queueUserConfirmedAt']
 except Exception as error:
  result.update(error=str(error),traceback=traceback.format_exc())
 finally:
  result['finishedAt']=national.stamp()
  if audit:
   try:audit.screenshot('final-screen');(audit.case_dir/'logcat.txt').write_text(audit.adb('logcat','-d'))
   except Exception as capture_error:result['captureError']=str(capture_error)
   try:audit.call('DELETE','')
   except Exception:pass
  write_json(args.out/'result.json',result)
 if not result['pass']:raise SystemExit(1)
 print(compact({k:result[k] for k in ['pass','caseId','sourceRecordId','apkSha256','androidApi','officialAutomaticCoverageContribution']}))

def main():
 p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
 a=sub.add_parser('plan');a.add_argument('--apk-url',required=True);a.add_argument('--apk-sha256',required=True);a.add_argument('--apk-size',required=True,type=int);a.add_argument('--version-code',type=int,required=True);a.add_argument('--version',required=True);a.add_argument('--case-id');a.add_argument('--out',type=pathlib.Path,required=True)
 a=sub.add_parser('run');a.add_argument('--apk',required=True,type=pathlib.Path);a.add_argument('--plan',required=True,type=pathlib.Path);a.add_argument('--plan-sha256',required=True);a.add_argument('--api',required=True,type=int,choices=[30,35,36]);a.add_argument('--out',required=True,type=pathlib.Path)
 args=p.parse_args();globals()[args.action](args)
if __name__=='__main__':main()
