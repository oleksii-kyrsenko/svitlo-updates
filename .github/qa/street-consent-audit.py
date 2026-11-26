"""Separate real UI consent scenarios; never contribute to automatic coverage."""
import argparse,hashlib,importlib.util,json,pathlib,re,subprocess,time,traceback
HERE=pathlib.Path(__file__).resolve().parent
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
historical=load('historical_scaffold',HERE/'historical-hint-audit.py');national=historical.national
controls=load('street_controls',HERE/'native90/street-controls.py');native=load('native_contract',HERE/'native90/contract.py')
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')

class NotExercised(RuntimeError):pass
class ConsentAudit(historical.HistoricalAudit):
 def tap(self,label,scroll=False,required=True):
  if getattr(self,'scenario_active',False):
   if label in ['Застосувати введену вулицю','Застосувати номер будинку']:
    self.not_exercised='exact-postal-street-or-house-not-listed';raise NotExercised(self.not_exercised)
   if label=='save-place' and not getattr(self,'choice_attempted',False):
    self.choice_attempted=True;self.perform_choice()
  return super().tap(label,scroll,required)
 def observe_post_save_queue(self,case,result,state,place,deadline):
  # Explicit user consent starts a different lookup; automatic audits retain
  # their original deadline and never instantiate this subclass.
  return super().observe_post_save_queue(case,result,state,place,self.choice_deadline)
 def appearance(self):
  reference=national.result_evidence.capture_reference(self.case_dir,self.last_state_capture)
  file=next(x for x in reference['files'] if pathlib.Path(x['path']).name=='RKStorage')
  with national.result_evidence.read_only_capture(self.case_dir/file['path']) as db:
   row=db.execute('SELECT value FROM catalystLocalStorage WHERE key=?',('svitlo.appearance.v1',)).fetchone()
  return json.loads(row[0]) if row else None
 def capture_state(self,label):
  state=self.read_state();projection=controls.projected(state,self.appearance());write(self.case_dir/(label+'.json'),{'observed':projection,'readOnlyCapture':self.last_state_capture});return state,projection
 def scan_end(self,down,seen,label):
  previous=None;stable=0
  for page in range(24):
   xml=self.source();found=controls.choices(xml,self.size['width'],self.size['height'])
   for key,value in found.items():
    if key in seen and seen[key]!=value:self.not_exercised='source-choice-literal-changed';raise NotExercised(self.not_exercised)
    seen[key]=value
   (self.case_dir/(label+'-'+str(page).zfill(2)+'.xml')).write_text(xml)
   signature=controls.frame_signature(xml,self.size['width'],self.size['height']);stable=stable+1 if signature==previous else 0;previous=signature
   if stable>=2:return
   self.scroll(down)
  self.not_exercised='source-choice-scan-did-not-reach-stable-end';raise NotExercised(self.not_exercised)
 def android_clock(self):
  value=self.adb('shell','date','+%s').strip()
  if not re.fullmatch(r'[1-9]\d{8,11}',value):raise RuntimeError('Android wall clock was not readable')
  return int(value)
 def perform_choice(self):
  seen={};self.scan_end(False,seen,'scan-to-top');self.scan_end(True,seen,'scan-to-bottom');write(self.case_dir/'all-source-choice-ids.json',seen)
  if len(seen)!=1:
   self.not_exercised='no-source-choice' if not seen else 'multiple-source-choices';raise NotExercised(self.not_exercised)
  key=next(iter(seen));self.scan_end(False,seen,'reacquire-top')
  if set(seen)!={key}:self.not_exercised='source-choices-changed-before-click';raise NotExercised(self.not_exercised)
  for _ in range(24):
   xml=self.source()
   try:self.choice=controls.visible_choice(xml,key,self.target['exactHouse'],self.size['width'],self.size['height']);break
   except ValueError:
    self.scroll()
  else:raise RuntimeError('Unique source choice and its warning/last house component were not visibly bound')
  self.screenshot('before-explicit-choice',xml);write(self.case_dir/'before-choice-visible-binding.json',self.choice)
  _,self.before_projection=self.capture_state('before-choice-state')
  fresh=self.source();binding=controls.visible_choice(fresh,key,self.target['exactHouse'],self.size['width'],self.size['height'])
  if binding['sourceLabel']!=self.choice['sourceLabel']:self.not_exercised='source-choice-literal-changed-before-click';raise NotExercised(self.not_exercised)
  self.screenshot('immediately-before-explicit-choice',fresh);box=binding['buttonBounds'];before=self.android_clock();started=time.monotonic();self.adb('shell','input','tap',str((box[0]+box[2])//2),str((box[1]+box[3])//2));after=self.android_clock();elapsed=time.monotonic()-started
  if after<before or abs((after-before)-elapsed)>3:raise RuntimeError('Android wall clock changed during the explicit click')
  self.clock_window=[before*1000,(after+1)*1000-1];write(self.case_dir/'android-click-clock.json',{'beforeSeconds':before,'afterSeconds':after,'elapsedMonotonicSeconds':elapsed,'measurementPrecisionMs':1000,'acceptedAndroidMilliseconds':self.clock_window,'hostWallClockUsedForMarkerValidation':False,'clickMethod':'real input tap at freshly validated exact testID bounds','buttonId':key,'buttonBounds':box})
  self.choice_deadline=time.monotonic()+150;self.visible_selected_queue=None;self.choice_timed_out=False
  while time.monotonic()<self.choice_deadline:
   current=self.source();queue=controls.visible_selected_queue(current,self.size['width'],self.size['height'])
   if queue:self.visible_selected_queue=queue;self.screenshot('after-choice-before-save',current);return
   if not national.queue_lookup_pending(' '.join(self.texts(current))) and time.monotonic()-started>12:
    self.screenshot('after-choice-source-not-ready',current);return
   time.sleep(1)
  self.choice_timed_out=True;self.screenshot('after-choice-source-timeout')
 def visible_saved(self,label,place,scope):
  # Stop once the actual top card is visible. Blind upward swipes at scroll0
  # trigger the app's real pull-to-refresh and race the offline cache check.
  for _ in range(24):
   if controls.home_top_visible(self.source(),self.size['width'],self.size['height']):break
   self.scroll(False)
  else:raise RuntimeError('Could not reacquire the visible saved top card without overscrolling')
  for page in range(24):
   xml=self.source();binding=historical.historical_screen.visible_notice(xml,scope,self.size['width'],self.size['height']);texts=binding['texts']
   valid=(place['address'] in texts and any(re.match(r'^Черга\s+'+re.escape(place['queue'])+r'(?:\s|$)',text) for text in texts)) if scope=='schedule-source' else any('Адресу зіставлено після вашого підтвердження.' in text and place['queueStreetSelection']['source']['street'] in text for text in texts)
   if valid:self.screenshot(label,xml);write(self.case_dir/(label+'-binding.json'),binding);return
   self.scroll()
  raise RuntimeError('Saved source card or explicit-consent notice is not actually visible: '+scope)

def run(args):
 meta=json.loads((HERE/'native90/meta.json').read_text());native.validate_metadata(meta,json.loads((HERE/'native90/baseline-89.json').read_text()))
 sample=HERE/'capital-baseline.json';raw=sample.read_bytes()
 if hashlib.sha256(raw).hexdigest()!=controls.SAMPLE_SHA:raise ValueError('Frozen original sample changed')
 if {'api':args.api,'caseId':args.case_id} not in controls.CASES:raise ValueError('Street-consent case/API mapping is not the original three-case matrix')
 cases,_,_=national.attach_reviewed_display_variants(json.loads(raw)['cases'],controls.SAMPLE_SHA);case=next(c for c in cases if c['id']==args.case_id)
 contract=national.audit_contract.contract({'apkUrl':native.candidate_url(meta),'apkSha256':meta['sha256'],'apkSize':meta['size'],'versionCode':meta['versionCode'],'version':meta['version'],'sample':'.github/qa/capital-baseline.json','androidApi':args.api})
 if (args.out/case['id']).exists():raise ValueError('Use a fresh output directory; earlier consent attempts must remain unchanged')
 args.out.mkdir(parents=True,exist_ok=True);write(args.out/'contract.json',contract);national.audit_contract.verify_apk(args.apk,contract,diagnostics=args.out/'binary')
 subprocess.run(['adb','root'],check=True,capture_output=True,timeout=45);subprocess.run(['adb','wait-for-device'],check=True,timeout=60)
 audit=None;result={'kind':'explicit-source-street-real-ui-acceptance-not-automatic-coverage','caseId':case['id'],'androidApi':args.api,'apkSha256':meta['sha256'],'originalFrozenHouse':case['exactHouse'],'officialAutomaticCoverageContribution':0,'independentlyQualifiedCorrect':None,'independentQualificationStatus':'pending','pass':False,'outcome':'FAIL'}
 try:
  audit=ConsentAudit(args.apk,args.out,contract);audit.target=case;audit.scenario_active=True;audit.choice_attempted=False;audit.not_exercised=None
  original=audit.run_case(case);result['originalUIAttempt']=original
  if audit.not_exercised:result.update(outcome='NOT_EXERCISED',reason=audit.not_exercised);return result
  if original.get('outcome')=='harness_error':raise RuntimeError('Original UI attempt failed: '+str(original.get('automationError')))
  state,saved=audit.capture_state('saved-consent-state');place=saved['place']
  if not place:raise RuntimeError('Ordinary Save did not persist the selected address')
  national.validate_saved_address(case,original,place)
  if place.get('addressOrigin')!='postal':raise RuntimeError('Consent acceptance requires the original ordinary postal selections')
  marker=controls.validate_marker(place,case,audit.choice,audit.clock_window)
  if not controls.same_value(saved['settings'],audit.before_projection['settings']) or not controls.same_value(saved['appearance'],audit.before_projection['appearance']):raise RuntimeError('Choice or Save changed existing settings/appearance')
  result.update(actualClickedSource=audit.choice,androidClickClockWindow=audit.clock_window,actualSavedSource=marker['source'],savedPlaceId=place['id'])
  if getattr(audit,'choice_timed_out',False) or place.get('queueCheckStatus') in ['source_unavailable','source_protected','unsupported_format','integration_required','loading']:
   audit.screenshot('saved-source-not-exercised');result.update(outcome='NOT_EXERCISED',sourceStatus=place.get('queueCheckStatus'));return result
  if place.get('queueCheckStatus') in ['not_included','ambiguous','not_found','needs_selection','no_public_data']:
   audit.screenshot('saved-source-not-applicable');result.update(outcome='SOURCE_DATA_NOT_APPLICABLE',sourceStatus=place.get('queueCheckStatus'));return result
  controls.validate_ready(place,case,audit.choice,audit.clock_window,audit.visible_selected_queue)
  audit.visible_saved('after-save-source-card',place,'schedule-source');audit.visible_saved('after-save-user-choice-notice',place,'source-street-confirmed-notice')
  result['refreshIdleBeforeIsolation']=audit.wait_refresh_idle()
  result['offlineBeforeRestart']=audit.firewall(True);audit.adb('shell','am','force-stop',national.PKG);_,anchor=audit.capture_state('network-blocked-offline-anchor');controls.unchanged_saved(saved,anchor)
  audit.adb('shell','am','start','-W','-n',national.PKG+'/.MainActivity');audit.wait(lambda xml:'current-address-name' in xml,60);time.sleep(4)
  _,offline=audit.capture_state('offline-restart-state');controls.unchanged_saved(saved,offline);controls.validate_marker(offline['place'],case,audit.choice,audit.clock_window,marker)
  result['offlineCachePreservation']=controls.unchanged_ready_cache(anchor['cache'],offline['cache'])
  audit.visible_saved('offline-source-card',offline['place'],'schedule-source');audit.visible_saved('offline-user-choice-notice',offline['place'],'source-street-confirmed-notice');result['offlineAfterRestart']=audit.firewall(False)
  result.update({'pass':True,'outcome':'confirmed_source_street','confirmedQueue':place['queue'],'selectionTimestamp':marker['selectedAt']})
 except Exception as error:result.update(error=str(error),traceback=traceback.format_exc())
 finally:
  if audit:
   try:audit.screenshot('consent-final-screen');(audit.case_dir/'consent-logcat.txt').write_text(audit.adb('logcat','-d'))
   except Exception as error:result['diagnosticError']=str(error)
   try:audit.call('DELETE','')
   except Exception:pass
  write(args.out/'street-consent-result.json',result)
 return result

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--apk',required=True,type=pathlib.Path);parser.add_argument('--case-id',required=True);parser.add_argument('--api',required=True,type=int,choices=[30,35,36]);parser.add_argument('--out',required=True,type=pathlib.Path);args=parser.parse_args();result=run(args);print(json.dumps({k:result.get(k) for k in ['caseId','androidApi','pass','outcome','officialAutomaticCoverageContribution']},ensure_ascii=False))
 if not result['pass']:raise SystemExit(1)
if __name__=='__main__':main()
