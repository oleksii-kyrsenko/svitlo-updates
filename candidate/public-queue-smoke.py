"""Synthetic persisted-state UI control, not a live address/coverage result."""
import pathlib,json,sqlite3,time
source=pathlib.Path('candidate/apk-smoke.py').read_text().split('flags={}')[0]
c={'__name__':'public_queue_helpers'};exec(compile(source,'public-queue-ui-helpers','exec'),c)
adb=c['adb'];out=c['out'];pkg=c['pkg'];launch=c['launch'];wait=c['wait_source'];evidence=c['evidence'];flags={}
def seed(state,name):
 dbfile=out/(name+'-storage.db')
 with sqlite3.connect(dbfile) as db:
  db.execute('CREATE TABLE catalystLocalStorage (key TEXT PRIMARY KEY,value TEXT NOT NULL)');db.execute('PRAGMA user_version=1');db.execute('INSERT INTO catalystLocalStorage VALUES (?,?)',('svitlo.state.v1',json.dumps(state,ensure_ascii=False)))
 adb('shell','am','force-stop',pkg);adb('shell','pm','clear',pkg)
 remote=f'/data/data/{pkg}/databases';adb('shell','mkdir','-p',remote);adb('push',str(dbfile),remote+'/RKStorage');uid=adb('shell','stat','-c','%u',f'/data/data/{pkg}').strip();assert uid.isdigit()
 adb('shell','chown','-R',f'{uid}:{uid}',remote);adb('shell','restorecon','-R',remote)
try:
 adb('shell','svc','wifi','disable');adb('shell','svc','data','disable')
 state=json.loads(pathlib.Path('candidate/fixture.json').read_text());p=state['places'][0];now=int(adb('shell','date','+%s').strip())*1000
 p.update(queueOrigin='public',queueEvidence='public-message',queueScope='house',queueCheckedAt=now,queuePublicPublishedAt=now-3600000,queuePublicExpiresAt=now+86400000,queueSource='https://example.invalid/qa-only/publication',queueOfficialStatus='source_unavailable',queueCheckStatus='ready',queueTransport=None,queuePublicValidity={'from':'2026-10-01','to':'2027-04-01','quote':'Перелік діє з 1.10.2026 до 1.04.2027 року'})
 seed(state,'provisional');launch();s=wait('Ймовірна черга 3.1');evidence('public-queue-provisional',s);flags['provisionalLabel']=True
 for _ in range(5):
  s=c['xml']()
  if 'Не підтверджено оператором' in s:break
  c['scroll_down'](c['E'].fromstring(s))
 assert 'Не підтверджено оператором' in s and 'Це не означає' in s;evidence('public-queue-warning',s);flags['warningAndOfficialFailureDistinction']=True
 assert 'Період переліку' in s and '2027-04-01' in s;flags['explicitPeriodVisible']=True
 launch();s=wait('Ймовірна черга 3.1');evidence('public-queue-after-restart',s);flags['restartPreservesProvisionalLabel']=True
 p['queuePublicExpiresAt']=now-1;seed(state,'expired');launch();s=wait('Чергу ще не визначено');evidence('public-queue-expired',s);flags['expiredQueueRetracted']=True
finally:
 result={'api':adb('shell','getprop','ro.build.version.sdk').strip(),'apkSha256':c['meta']['sha256'],'flags':flags,'allPassed':len(flags)==5 and all(flags.values()),'method':'synthetic saved-state UI control, not live queue lookup'}
 (out/'public-queue-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print('PUBLIC_QUEUE_UI_RESULT',json.dumps(result),flush=True)
