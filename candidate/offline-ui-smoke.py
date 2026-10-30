"""Actual APK offline retention; external QA plans, network disabled on emulator."""
import pathlib,json,time,copy,datetime,zoneinfo,xml.etree.ElementTree as E
prefix=pathlib.Path('candidate/settings-ui-smoke.py').read_text().split('\ntry:')[0]
c={'__name__':'offline_helpers'};exec(compile(prefix,'offline_helpers','exec'),c)
adb=c['adb'];xml=c['xml'];tap=c['tap'];wait=c['wait'];seed=c['seed'];launch=c['launch'];evidence=c['evidence'];out=c['out'];pkg=c['pkg'];bounds=c['c']['bounds'];scroll=c['scroll'];flags={}
def find(label):
 for _ in range(16):
  s=xml();tree=E.fromstring(s)
  nodes=[n for n in tree.iter('node') if label in [n.get('text'),n.get('content-desc'),n.get('resource-id','').split('/')[-1]] and len(bounds(n))==4 and bounds(n)[2]>bounds(n)[0] and bounds(n)[3]-bounds(n)[1]>30]
  if nodes:return s,nodes[0]
  scroll(tree)
 raise AssertionError('Offline label not visible: '+label)
def verify(state,plans,p):
 days=state['snapshots'][p['id']]
 for key in ['today','tomorrow']:
  value=days[key];expected=plans[key];assert value['date']==expected['date'] and value['intervals']==expected['intervals'];assert value['checkedAt']==expected['checkedAt'] and value['validUntil']==expected['validUntil'];assert value.get('refreshError') and value['status']=='ready'
 return days
try:
 adb('shell','svc','wifi','disable');adb('shell','svc','data','disable')
 state=json.loads(pathlib.Path('candidate/fixture.json').read_text());p=state['places'][0];p.update(queue='3.1',queueOrigin='manual',queueConfirmed=True);state.update(activePlaceId=p['id'],notificationsEnabled=False)
 stamp=int(adb('shell','date','+%s').strip());tz=zoneinfo.ZoneInfo('Europe/Kyiv');date=datetime.datetime.fromtimestamp(stamp,tz).date();checked=datetime.datetime.fromtimestamp(stamp-60,datetime.timezone.utc).isoformat().replace('+00:00','Z')
 def plan(offset,ranges):
  d=date+datetime.timedelta(days=offset)
  def instant(text):
   hour,minute=map(int,text.split(':'));return int(datetime.datetime.combine(d,datetime.time(0),tzinfo=tz).timestamp()*1000+(hour*60+minute)*60000)
  return {'operatorId':p['operatorId'],'queue':p['queue'],'queueAdapter':p.get('queueAdapter'),'date':d.isoformat(),'status':'ready','provenance':'official','checkedAt':checked,'validUntil':(stamp+600)*1000,'sourceUrl':'https://www.cherkasyoblenergo.com/','intervals':[{'start':a,'end':b,'startAt':instant(a),'endAt':instant(b)} for a,b in ranges]}
 plans={'today':plan(0,[('10:00','12:00'),('22:00','24:00')]),'tomorrow':plan(1,[('14:00','16:00')])};state['snapshots']={p['id']:copy.deepcopy(plans)}
 seed(state);wait('schedule-cache-warning');s,_=find('timeline-card-1320-1440');flags['fullTodayRetainedAfterFailure']=True;evidence('offline-saved-today',s)
 assert not any(n.get('class')=='android.widget.ProgressBar' for n in E.fromstring(s).iter('node'));flags['noBackgroundLoader']=True
 stored=c['state_read']();verify(stored,plans,p);flags['originalVerificationAndExpiryRetained']=True
 launch();wait('schedule-cache-warning');s,_=find('timeline-card-1320-1440');flags['cacheSurvivesOfflineRestart']=True;evidence('offline-after-restart',s)
 c['top']();tap('Завтра');wait('schedule-cache-warning');s,_=find('timeline-card-840-960');flags['fullTomorrowRetained']=True;evidence('offline-saved-tomorrow',s)
 c['source_wait']('Оновити графік');s,button=find('schedule-refresh');assert button.get('enabled')=='true' and button.get('class')=='android.widget.Button';tap('Оновити графік');s=wait('schedule-refresh-result','Оновлення недоступне');flags['manualRefreshButtonReallyWorks']=True;evidence('offline-manual-refresh-result',s)
 verify(c['state_read'](),plans,p);flags['manualFailureDoesNotEraseCache']=True
 empty=copy.deepcopy(state);empty['snapshots']={};seed(empty);s=wait('Не вдалося отримати графік');assert 'timeline-card-' not in s;flags['emptyCacheDoesNotInventIntervals']=True;evidence('offline-without-saved-plan',s)
finally:
 result={'api':adb('shell','getprop','ro.build.version.sdk').strip(),'flags':flags,'apkSha256':c['c']['meta']['sha256'],'allPassed':len(flags)==8 and all(flags.values()),'scope':'External QA plans in actual signed APK; emulator wifi/data disabled, full retained intervals/original verification and expiry, restart, real refresh action and empty-cache behavior. Physical phone and live source recovery not asserted.'};(out/'offline-ui-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print('OFFLINE_UI_RESULT',json.dumps(result),flush=True)
