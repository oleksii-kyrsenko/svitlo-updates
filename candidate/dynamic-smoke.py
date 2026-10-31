"""External proposal UI QA; synthetic data stays outside the application APK.
Run from public QA checkout containing candidate/apk-smoke.py, meta.json, fixture.json.
Requires root emulator; install candidate APK before this script.
"""
import pathlib,json,sqlite3,time,copy,xml.etree.ElementTree as E
c={'__name__':'dynamic_helpers'}
exec(compile(pathlib.Path('candidate/apk-smoke.py').read_text().split('\nflags={}')[0],'dynamic_helpers','exec'),c)
adb=c['adb'];xml=c['xml'];tap=c['tap'];wait=c['wait_for'];launch=c['launch'];out=c['out'];pkg=c['pkg'];evidence=c['evidence']
flags={}
def seed(state,extra=None):
 adb('shell','am','force-stop',pkg)
 local=out/'dynamic-RKStorage';local.unlink(missing_ok=True)
 with sqlite3.connect(local) as db:
  db.execute('CREATE TABLE catalystLocalStorage(key TEXT PRIMARY KEY,value TEXT NOT NULL)');db.execute('PRAGMA user_version=1')
  for key,value in [('svitlo.state.v1',state),('svitlo.appearance.v1',{'version':1,'theme':'aurora'})]+list((extra or {}).items()):db.execute('INSERT INTO catalystLocalStorage VALUES (?,?)',(key,json.dumps(value,ensure_ascii=False)))
 remote=f'/data/data/{pkg}/databases'
 adb('shell','mkdir','-p',remote)
 for name in ['RKStorage','RKStorage-wal','RKStorage-shm','RKStorage-journal']:adb('shell','rm','-f',remote+'/'+name)
 adb('push',str(local),remote+'/RKStorage');uid=adb('shell','stat','-c','%u',f'/data/data/{pkg}').strip();assert uid.isdigit()
 adb('shell','chown','-R',f'{uid}:{uid}',remote);adb('shell','restorecon','-R',remote)
def saved():
 adb('shell','am','force-stop',pkg)
 target=out/('dynamic-saved-'+str(time.time_ns()));target.mkdir()
 adb('pull',f'/data/data/{pkg}/databases',str(target))
 with sqlite3.connect(target/'databases'/'RKStorage') as db:return json.loads(db.execute('SELECT value FROM catalystLocalStorage WHERE key=?',('svitlo.state.v1',)).fetchone()[0])
def fixture():
 state=json.loads(pathlib.Path('candidate/fixture.json').read_text());p=state['places'][0]
 p.update(queue=None,queueConfirmed=False,queueOrigin=None,queueUserConfirmedAt=None,queuePublicConflict=True)
 p['reminders']['enabled']=True
 stamp=int(adb('shell','date','+%s').strip())*1000
 identity=json.dumps([p.get('operatorId') or '',p.get('regionId') or '',p.get('address') or '',p.get('addressParts'),p.get('addressContext'),p.get('officialCityId')],ensure_ascii=False,separators=(',',':'))
 source={'url':'https://example.org/qa/local-message','quote':'Синтетична QA-публікація: будинок, черга 2.2','publishedAt':stamp-3600000}
 common={'origin':'public','operatorId':p['operatorId'],'scope':'house','sourceUrl':source['url'],'publicQuote':source['quote'],'publicPublishedAt':source['publishedAt'],'publicExpiresAt':stamp+86400000,'publicSources':[source],'addressIdentity':identity}
 p['queuePublicCandidates']=[dict(common,id='native-direct',queue='2.2',publicMethod='direct'),dict(common,id='native-inferred',queue='3.1',publicMethod='inferred',publicReasoning='Зіставлено місцеві QA-повідомлення')]
 state.update(places=[p],activePlaceId=p['id'],snapshots={},notificationsEnabled=False,gpsAsked=True,endpoint='')
 return state
try:
 adb('root',check=False);adb('wait-for-device');adb('shell','svc','wifi','disable');adb('shell','svc','data','disable')
 state=fixture();seed(state);launch();wait('public-queue-proposals');evidence('dynamic-public-proposals',xml());flags['proposalsVisibleWithoutAutomaticQueue']=True
 tap('confirm-public-candidate-native-direct',scroll=True);time.sleep(2)
 actual=saved()['places'][0]
 assert actual['queue']=='2.2' and actual['queueOrigin']=='public' and actual['queueConfirmed'] is True and actual.get('queueUserConfirmedAt')
 assert actual['reminders']['enabled'] is False
 flags['explicitChoicePreservesPublicOriginAndDisablesReminders']=True
 launch();wait('current-address-card');c['wait_source']('Редагувати адресу');evidence('dynamic-public-selected',xml())
 actual=saved()['places'][0];assert actual['queue']=='2.2' and actual['queueOrigin']=='public';flags['choiceSurvivesRestartOffline']=True
 # Real signed data, generated after the client code: seed only delivery cache,
 # then obtain the queue through the actual app lookup rather than seed a queue.
 import base64,hashlib
 env=json.loads(pathlib.Path('candidate/dynamic-manifest.json').read_text())
 manifest=json.loads(base64.b64decode(env['payload']))
 entry=next(e for e in manifest['bundles'] if e['operatorId']=='lviv')
 bundle_text=pathlib.Path('candidate/dynamic-lviv-bundle.json').read_text()
 assert hashlib.sha256(bundle_text.encode()).hexdigest()==entry['sha256'] and len(bundle_text.encode())==entry['size']
 bundle=json.loads(bundle_text);row=next(r for r in bundle['records'] if r['scope']=='house')
 device_now=int(adb('shell','date','+%s').strip())*1000
 assert row['expiresAt']>device_now and manifest['expiresAt']>device_now,'Real delivery snapshot expired; refresh official collector before retry'
 state=fixture();p=state['places'][0]
 p.update(address=', '.join([row['settlement'],row['street'],row['houses'][0]]),addressParts={'settlement':row['settlement'],'street':row['street'],'house':row['houses'][0]},addressContext={'regionId':row['regionId'],'community':row['community']},latitude=49.87,longitude=24.04,regionId=row['regionId'],operatorId='lviv',operatorOrigin='manual',officialCityId=None,queue=None,queueConfirmed=False,queueOrigin=None,queuePublicCandidates=[],queuePublicConflict=False)
 extra={'@svitlo/dynamic-coverage-v1':env,'@svitlo/dynamic-coverage-v1/lviv':{'sha256':entry['sha256'],'text':bundle_text}}
 seed(state,extra);launch();c['wait_source']('Черга '+row['queue']);time.sleep(2);evidence('dynamic-official-delivery',xml())
 resolved=saved()['places'][0]
 assert resolved['queue']==row['queue'] and resolved['queueOrigin']=='official' and resolved['queueEvidence']=='dynamic-roster',resolved
 assert resolved['queueCheckedAt']==row['checkedAt'] and resolved['queueSource']==row['sourceUrl']
 flags['RealSignedRosterResolvesWithoutSeededQueueOrNewAPK']=True
 state=fixture()
 for candidate in state['places'][0]['queuePublicCandidates']:candidate['publicExpiresAt']=1
 seed(state);launch();wait('current-address-card');time.sleep(3)
 assert 'confirm-public-candidate-' not in xml();evidence('dynamic-expired-proposals',xml());flags['expiredCandidatesNotOffered']=True
finally:
 result={'api':adb('shell','getprop','ro.build.version.sdk').strip(),'savedTheme':__import__('os').environ['SAVED_THEME'],'apkSha256':c['meta']['sha256'],'flags':flags,'allPassed':len(flags)==5 and all(flags.values()),'scope':'External synthetic proposal fixtures; direct/inferred presentation, explicit selection, public provenance, reminders off, offline restart and expiry. Real signed official roster delivered through persisted remote cache resolves an unseeded queue offline; this is a sampled delivery check, not national coverage.'}
 (out/'dynamic-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print('DYNAMIC_RESULT',json.dumps(result),flush=True)
