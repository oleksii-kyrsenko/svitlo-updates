"""Read-only diagnosis of the observed black startup/interaction failure.

No queue lookup, address selection, storage seeding or product changes. Each
ordinary input phase retains actual PNG/XML, logcat and Android service state.
"""
import hashlib, importlib.util, json, pathlib, subprocess, time, traceback
import xml.etree.ElementTree as ET
from PIL import Image

ROOT=pathlib.Path('.github/qa');OUT=pathlib.Path('startup-diagnostic');OUT.mkdir(exist_ok=True)
spec=importlib.util.spec_from_file_location('audit',ROOT/'national-address-audit.py');audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
contract=json.loads((OUT/'contract.json').read_text());request=json.loads((ROOT/'startup-diagnostic-request.json').read_text())
if contract['apkSha256']!=request['apkSha256']:raise ValueError('Diagnostic APK differs from the requested failure binary')
report={'schemaVersion':1,'scope':'diagnostic only; not address coverage','sourceFailureRun':request['sourceFailureRun'],'apkSha256':contract['apkSha256'],'phases':[],'noAddressStorageSeeding':True,'noQueueInputs':True}
driver=None

def command(args,path):
    value=subprocess.run(['adb',*args],capture_output=True,text=True,timeout=40)
    path.write_text(value.stdout+'\nSTDERR\n'+value.stderr)
    return value.returncode

def services(label):
    for service in ['window','SurfaceFlinger','input']:
        command(['shell','dumpsys',service],OUT/(label+'-'+service+'.txt'))
    command(['logcat','-d','-v','threadtime'],OUT/(label+'-logcat.txt'))

def raw_source():return driver.call('GET','/source')

def capture(label):
    xml=raw_source();driver.screenshot(label,xml);png=driver.case_dir/(label+'.png')
    with Image.open(png).convert('RGB') as image:
        w,h=image.size;body=image.crop((0,80,w,max(81,h-80)));pixels=body.getdata();black=sum(1 for pixel in pixels if max(pixel)==0)/max(1,body.width*body.height)
    services(label)
    return xml,{'png':str(png.relative_to(OUT)),'pngSha256':hashlib.sha256(png.read_bytes()).hexdigest(),'xmlSha256':hashlib.sha256(xml.encode()).hexdigest(),'blackBodyFraction':round(black,5),'editorVisible':'Обрати: Область' in xml,'homeVisible':'Ввести адресу' in xml}

try:
    driver=audit.Audit(pathlib.Path('artifacts/candidate.apk'),OUT,contract)
    driver.case_dir=OUT/'observations';driver.case_dir.mkdir(exist_ok=True)
    for index,mode in enumerate(['accessibility','physical','accessibility']):
        label=str(index+1)+'-'+mode
        if index:
            driver.adb('shell','am','force-stop',audit.PKG)
            driver.adb('shell','monkey','-p',audit.PKG,'-c','android.intent.category.LAUNCHER','1')
            deadline=time.monotonic()+20
            while time.monotonic()<deadline:
                if 'Ввести адресу' in raw_source():break
                time.sleep(.5)
        xml,before=capture(label+'-before');nodes=[n for n in ET.fromstring(xml).iter() if n.get('content-desc')=='Ввести адресу' and n.get('enabled')!='false' and n.get('displayed')!='false']
        phase={'index':index+1,'mode':mode,'freshProcess':bool(index),'before':before}
        if len(nodes)!=1 or not driver.box(nodes[0]):
            phase.update(error='Exactly one enabled entry button with actual bounds was not available');report['phases'].append(phase);continue
        node=nodes[0];phase['actualButtonBounds']=node.get('bounds');started=time.monotonic()
        if mode=='physical':
            b=driver.box(node);driver.adb('shell','input','tap',str((b[0]+b[2])//2),str((b[1]+b[3])//2))
        else:driver.click_node(node)
        deadline=time.monotonic()+12
        while time.monotonic()<deadline:
            if 'Обрати: Область' in raw_source():break
            time.sleep(.5)
        phase['secondsAfterInput']=round(time.monotonic()-started,3)
        _,phase['after']=capture(label+'-after');report['phases'].append(phase)
    report['allPhasesResponded']=all(p.get('after',{}).get('editorVisible') and p['after']['blackBodyFraction']<.98 for p in report['phases']) and len(report['phases'])==3
    report['limitations']=['The first launch is cold; later fresh processes retain only ordinary app-created caches. An A/B/A difference cannot alone prove the input method caused a failure.','A successful diagnostic does not erase the five original failures or establish address coverage.']
except Exception as error:
    report.update(errorType=type(error).__name__,error=str(error),traceback=traceback.format_exc())
finally:
    try:services('final')
    except Exception as error:report['finalServicesError']=type(error).__name__
    if driver and driver.sid:
        try:driver.call('DELETE','')
        except Exception:pass
    (OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({key:report.get(key) for key in ['allPhasesResponded','errorType','scope']}))
