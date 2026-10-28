"""Black-box cache failover test. Only test-emulator hosts are modified."""
import pathlib,json,sqlite3,re,time
source=pathlib.Path('candidate/apk-smoke.py').read_text().split('flags={}')[0]
context={'__name__':'cache_test_helpers'};exec(compile(source,'public-apk-test-helpers','exec'),context)
adb=context['adb'];out=context['out'];pkg=context['pkg'];launch=context['launch'];wait=context['wait_for'];evidence=context['evidence']
flags={}
try:
    adb('root',check=False);adb('wait-for-device')
    adb('shell','svc','wifi','enable');adb('shell','svc','data','enable');time.sleep(3)
    hosts=adb('shell','cat','/system/etc/hosts')+'\n127.0.0.1 hoe.com.ua\n::1 hoe.com.ua\n'
    file=out/'test-hosts';file.write_text(hosts);adb('push',str(file),'/data/local/tmp/svitlo-test-hosts')
    adb('shell','chmod','644','/data/local/tmp/svitlo-test-hosts');adb('shell','chcon','u:object_r:system_file:s0','/data/local/tmp/svitlo-test-hosts')
    pids=['1']
    for name in ['zygote64','zygote','netd']:
        pids += [p for p in adb('shell','pidof',name,check=False).split() if p.isdigit()]
    for pid in dict.fromkeys(pids):
        adb('shell','nsenter','--mount=/proc/'+pid+'/ns/mnt','--','mount','--bind','/data/local/tmp/svitlo-test-hosts','/system/etc/hosts')
    ping=adb('shell','ping','-c','1','-W','2','hoe.com.ua',check=False)
    (out/'blocked-operator-host.txt').write_text(ping)
    assert '127.0.0.1' in ping or '::1' in ping,'Operator host did not resolve to loopback'
    flags['operatorHostBlocked']=True
    state=json.loads(pathlib.Path('candidate/cache-fixture.json').read_text())
    fixture=out/'cache-RKStorage'
    with sqlite3.connect(fixture) as db:
        db.execute('CREATE TABLE catalystLocalStorage(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
        db.execute('PRAGMA user_version=1')
        db.execute('INSERT INTO catalystLocalStorage VALUES(?,?)',('svitlo.state.v1',json.dumps(state,ensure_ascii=False)))
    adb('shell','am','force-stop',pkg);adb('shell','pm','clear',pkg)
    remote=f'/data/data/{pkg}/databases/RKStorage';adb('shell','mkdir','-p',f'/data/data/{pkg}/databases')
    adb('push',str(fixture),remote);uid=adb('shell','stat','-c','%u',f'/data/data/{pkg}').strip();assert uid.isdigit()
    adb('shell','chown','-R',f'{uid}:{uid}',f'/data/data/{pkg}/databases');adb('shell','restorecon','-R',f'/data/data/{pkg}/databases')
    launch();screen=wait('Черга 5.1','Збережена копія офіційного переліку');evidence('public-cache-ready',screen)
    flags['queueResolvedThroughPublicCache']=True
    launch();screen=wait('Черга 5.1','Збережена копія офіційного переліку');evidence('public-cache-after-restart',screen)
    flags['cachedQueueSurvivesRestart']=True
    adb('shell','am','force-stop',pkg);adb('pull',remote,str(out/'cache-persisted.db'))
    if 'yes' in adb('shell',f'test -f {remote}-wal && echo yes',check=False):adb('pull',remote+'-wal',str(out/'cache-persisted.db-wal'))
    with sqlite3.connect(out/'cache-persisted.db') as db:
        place=json.loads(db.execute('SELECT value FROM catalystLocalStorage WHERE key=?',('svitlo.state.v1',)).fetchone()[0])['places'][0]
    assert place['queue']=='5.1' and place['queueConfirmed'] and place['queueOrigin']=='official' and place['queueTransport']=='public-cache' and place['queueScope']=='house'
    stamp=int(adb('shell','date','+%s').strip())*1000
    assert 0<place['queueCheckedAt']==place['queueCacheFetchedAt']<=stamp<place['queueCacheExpiresAt']<=place['queueCacheFetchedAt']+12*3600000
    assert place['queueSource'].startswith('https://hoe.com.ua/Content/Uploads/') and place['address']==state['places'][0]['address']
    flags['officialSourceAndOriginalAgePreserved']=True
finally:
    result={'api':adb('shell','getprop','ro.build.version.sdk').strip(),'flags':flags,'allPassed':len(flags)==4 and all(flags.values())}
    (out/'cache-result.json').write_text(json.dumps(result,indent=2)+'\n');print('PUBLIC_CACHE_APK_RESULT',json.dumps(result),flush=True)
