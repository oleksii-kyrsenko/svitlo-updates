"""Black-box tests of the public APK. Fixture data never enters the APK."""
import pathlib,subprocess,json,sqlite3,time,re,xml.etree.ElementTree as E,os
root=pathlib.Path('.github/qa/native89');meta=json.loads((root/'meta.json').read_text());pkg=meta['packageName']
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
    if any(('Світло' in n.get('text','') or 'Коли світло' in n.get('text','')) and "isn't responding" in n.get('text','') for n in tree.iter('node')):
        (out/'app-anr.xml').write_text(s)
        (out/'app-anr-logcat.txt').write_text(adb('logcat','-d','-v','threadtime',check=False))
        subprocess.run(['adb','pull','/data/anr',str(out/'anr')],check=False)
        raise AssertionError('Application ANR; diagnostics captured')
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
    return list(map(int,re.findall(r'-?\d+',node.get('bounds',''))))
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
    if label in ['Видалити адресу','delete-place']:
        import importlib.util
        spec=importlib.util.spec_from_file_location('native_tap_target',root/'tap_target.py');target=importlib.util.module_from_spec(spec);spec.loader.exec_module(target)
        def retain(stage,s,selected,attempt,probe):
            name='delete-tap-'+str(attempt)+'-'+str(probe)+'-'+stage
            (out/(name+'.xml')).write_text(s)
            (out/(name+'.json')).write_text(json.dumps({'capturedAt':time.time(),'stage':stage,**selected},ensure_ascii=False,indent=2)+'\n')
            if stage!='tap':(out/(name+'.png')).write_bytes(subprocess.check_output(['adb','exec-out','screencap','-p'],timeout=60))
        target.activate_delete(xml,lambda x,y:adb('shell','input','tap',str(x),str(y)),scroll_down,retain,time.sleep)
        return
    for _ in range(8 if scroll else 1):
        r=E.fromstring(xml())
        for node in r.iter('node'):
            if label not in [node.get('text'),node.get('content-desc'),node.get('resource-id')]:continue
            b=list(map(int,re.findall(r'-?\d+',node.get('bounds',''))))
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
    top();deadline=time.monotonic()+150
    while True:
        s=xml();tree=E.fromstring(s)
        viewport=next((bounds(n) for n in tree.iter('node') if n.get('resource-id','').split('/')[-1]=='main-scroll'),[0,220,1080,1857])
        def visible(n):
            b=bounds(n)
            return len(b)==4 and b[2]>b[0] and b[3]>b[1] and b[1]>=viewport[1] and b[3]<=viewport[3]
        edit=next((n for n in tree.iter('node') if n.get('content-desc')=='Редагувати адресу' and visible(n)),None)
        if edit is not None and all(any(label in (n.get('text','')+' '+n.get('content-desc','')) and visible(n) for n in tree.iter('node')) for label in labels):return s
        if time.monotonic()>deadline:raise AssertionError('Source labels did not become visible: '+repr(labels))
        # Live schedule/history cards can arrive above this card while the request
        # is pending. Reacquire the source instead of waiting at stale coordinates.
        if edit is None or bounds(edit)[1]>viewport[3]-350:scroll_down(tree)
        else:time.sleep(1)


