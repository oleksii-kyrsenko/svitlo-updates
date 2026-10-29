"""Black-box tests of the public APK. Fixture data never enters the APK."""
import pathlib,subprocess,json,sqlite3,time,re,xml.etree.ElementTree as E,os
root=pathlib.Path('candidate');meta=json.loads((root/'meta.json').read_text());pkg=meta['packageName']
out=pathlib.Path('apk-diagnostics');out.mkdir(exist_ok=True)
def adb(*args,check=True):
    p=subprocess.run(['adb',*args],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=180)
    if check and p.returncode:raise RuntimeError(p.stdout)
    return p.stdout
def xml():
    adb('shell','rm','/sdcard/apk-qa.xml',check=False)
    for attempt in range(4):
        adb('shell','uiautomator','dump','/sdcard/apk-qa.xml',check=False)
        s=adb('shell','cat','/sdcard/apk-qa.xml',check=False)
        try:tree=E.fromstring(s);break
        except E.ParseError:
            if attempt==3:raise
            time.sleep(2)
    if any(n.get('text')=="Pixel Launcher isn't responding" for n in tree.iter('node')):
        recovered=getattr(xml,'launcher_recoveries',0);assert recovered<2,'Pixel Launcher repeatedly failed'
        xml.launcher_recoveries=recovered+1
        (out/('launcher-anr-'+str(recovered)+'.xml')).write_text(s)
        close=next(n for n in tree.iter('node') if n.get('resource-id')=='android:id/aerr_close');b=list(map(int,re.findall(r'\d+',close.get('bounds',''))));assert len(b)==4
        adb('shell','input','tap',str((b[0]+b[2])//2),str((b[1]+b[3])//2));time.sleep(2)
        adb('shell','am','start','-W','-n',pkg+'/.MainActivity');return xml()
    (out/'last-window.xml').write_text(s)
    return s
def wait_for(*labels):
    deadline=time.monotonic()+120
    while True:
        s=xml()
        if all(label in s for label in labels):return s
        if time.monotonic()>deadline:raise AssertionError('Missing screen labels: '+repr(labels))
        time.sleep(2)
def bounds(node):
    return list(map(int,re.findall(r'\d+',node.get('bounds',''))))
def wait_edit(value):
    deadline=time.monotonic()+20
    while True:
        s=xml()
        if any(n.get('class')=='android.widget.EditText' and n.get('text')==value for n in E.fromstring(s).iter('node')):return s
        if time.monotonic()>deadline:
            (out/'queue-input-failure.png').write_bytes(subprocess.check_output(['adb','exec-out','screencap','-p'],timeout=60))
            (out/'queue-input-method.txt').write_text(adb('shell','dumpsys','input_method'))
            raise AssertionError('Queue input did not contain '+repr(value))
        time.sleep(1)
def scroll_down(tree):
    candidates=[bounds(n) for n in tree.iter('node') if n.get('scrollable')=='true']
    candidates=[b for b in candidates if len(b)==4 and b[2]>b[0] and b[3]>b[1]]
    assert candidates,'No scrollable form'
    b=max(candidates,key=lambda b:(b[2]-b[0])*(b[3]-b[1]));x=(b[0]+b[2])//2;height=b[3]-b[1]
    adb('shell','input','swipe',str(x),str(b[1]+height*4//5),str(x),str(b[1]+height//4),'350');time.sleep(1)
def tap(label,scroll=False):
    for _ in range(8 if scroll else 1):
        r=E.fromstring(xml())
        for node in r.iter('node'):
            if label not in [node.get('text'),node.get('content-desc'),node.get('resource-id')]:continue
            b=list(map(int,re.findall(r'\d+',node.get('bounds',''))))
            if len(b)==4 and b[2]>b[0] and b[3]>b[1]:
                adb('shell','input','tap',str((b[0]+b[2])//2),str((b[1]+b[3])//2));time.sleep(1);return
        if scroll:scroll_down(r)
    raise AssertionError('Missing action: '+label)
def launch():
    adb('shell','am','force-stop',pkg)
    adb('shell','am','start','-W','-n',pkg+'/.MainActivity')
def evidence(name,s):
    (out/(name+'.xml')).write_text(s)
    (out/(name+'.png')).write_bytes(subprocess.check_output(['adb','exec-out','screencap','-p'],timeout=60))
    (out/(name+'-crashes.txt')).write_text(adb('logcat','-b','crash','-d'))
    assert ('Process: '+pkg) not in (out/(name+'-crashes.txt')).read_text()
def top():
    for _ in range(5):adb('shell','input','swipe','540','400','540','1500','220')
    time.sleep(.5)
def navigate(label):
    tap('Меню застосунку');tap(label)
def wait_source(*labels):
    top()
    for _ in range(12):
        s=xml();tree=E.fromstring(s)
        edits=[n for n in tree.iter('node') if n.get('content-desc')=='Редагувати адресу' and len(bounds(n))==4 and bounds(n)[3]>bounds(n)[1]]
        if edits:
            # Bring the entire address/queue row up from the bottom edge before reading it.
            if bounds(edits[0])[1]>1000:
                adb('shell','input','swipe','540','1500','540','850','300');time.sleep(.5)
            return wait_for(*labels)
        scroll_down(tree)
    raise AssertionError('Source address/edit row did not become visible')

flags={}
try:
    print(adb('root',check=False),flush=True);adb('wait-for-device')
    # Fixture-based UI/state checks; network isolation is not asserted.
    adb('shell','svc','wifi','disable');adb('shell','svc','data','disable')
    print(adb('install','-r','-g','--abi','x86_64','previous.apk'),flush=True)
    state=json.loads((root/'fixture.json').read_text());place=state['places'][0]
    place['queueCheckedAt']=int(adb('shell','date','+%s').strip())*1000
    fixture=out/'RKStorage'
    with sqlite3.connect(fixture) as db:
        db.execute('CREATE TABLE catalystLocalStorage (key TEXT PRIMARY KEY,value TEXT NOT NULL)')
        db.execute('PRAGMA user_version=1')
        db.execute('INSERT INTO catalystLocalStorage VALUES (?,?)',('svitlo.state.v1',json.dumps(state,ensure_ascii=False)))
    remote=f'/data/data/{pkg}/databases/RKStorage'
    adb('shell','am','force-stop',pkg);adb('shell','mkdir','-p',f'/data/data/{pkg}/databases')
    adb('push',str(fixture),remote)
    uid=adb('shell','stat','-c','%u',f'/data/data/{pkg}').strip();assert uid.isdigit()
    adb('shell','chown','-R',f'{uid}:{uid}',f'/data/data/{pkg}/databases')
    adb('shell','restorecon','-R',f'/data/data/{pkg}/databases')
    launch();s=wait_for('Романенка','Черга 3.1');evidence('previous',s);flags['previousReleaseVisible']=True
    print(adb('install','-r','-g','--abi','x86_64',str(root/meta['fileName'])),flush=True)
    launch();s=wait_source('Романенка','Черга 3.1');evidence('upgraded',s);flags['updatedPlacePreserved']=True
    tap('Редагувати адресу',scroll=True);tap('Виправити чергу, назву або оператора ⌄',scroll=True)
    field=None
    for _ in range(10):
        tree=E.fromstring(xml())
        field=next((n for n in tree.iter('node') if n.get('class')=='android.widget.EditText' and n.get('text')=='3.1' and len(bounds(n))==4 and bounds(n)[3]-bounds(n)[1]>=60),None)
        if field is not None:break
        scroll_down(tree)
    assert field is not None,'Queue input is not visible after scrolling'
    b=list(map(int,re.findall(r'\d+',field.get('bounds'))))
    adb('shell','input','tap',str((b[0]+b[2])//2),str((b[1]+b[3])//2));adb('shell','input','keyevent','123')
    api=int(adb('shell','getprop','ro.build.version.sdk').strip())
    if api>=33:
        # Replace the selection in one edit. Clearing the controlled value first
        # starts an address lookup whose optional connection panel moves this field.
        adb('shell','input','keycombination','113','29')
        adb('shell','input','text','2.2');wait_edit('2.2')
    else:
        for _ in range(3):adb('shell','input','keyevent','67')
        for part,value in [('2','2'),('.','2.'),('2','2.2')]:
            adb('shell','input','text',part);wait_edit(value)
    evidence('queue-value-before-save',wait_edit('2.2'))
    if re.search(r'\b(?:mInputShown|mIsInputViewShown|mInputViewShown)\s*[=:]\s*true',adb('shell','dumpsys','input_method')):adb('shell','input','keyevent','4')
    tap('Зберегти зміни',scroll=True);wait_source('Черга 2.2','вказано вами');flags['manualQueueEdited']=True
    launch();s=wait_source('Черга 2.2','вказано вами');evidence('manual-after-restart',s)
    adb('shell','am','force-stop',pkg);adb('pull',remote,str(out/'persisted.db'))
    if 'yes' in adb('shell',f'test -f {remote}-wal && echo yes',check=False):adb('pull',remote+'-wal',str(out/'persisted.db-wal'))
    with sqlite3.connect(out/'persisted.db') as db:
        actual=json.loads(db.execute('SELECT value FROM catalystLocalStorage WHERE key=?',('svitlo.state.v1',)).fetchone()[0])['places'][0]
    assert actual['address']==place['address'] and actual['queue']=='2.2' and actual['queueOrigin']=='manual'
    flags['manualQueueSurvivesRestart']=True
    assert 'Success' in adb('shell','pm','clear',pkg)
    launch();s=wait_for('Ввести адресу');evidence('cleared-data',s);flags['startsWithClearedData']=True
finally:
    result={'api':adb('shell','getprop','ro.build.version.sdk').strip(),'apkSha256':meta['sha256'],'scope':'fixture-based startup, update, manual correction, restart, cleared storage; live-source/graph/notification behavior and network isolation are not asserted','flags':flags,'allPassed':len(flags)==5 and all(flags.values())}
    (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result),flush=True)
