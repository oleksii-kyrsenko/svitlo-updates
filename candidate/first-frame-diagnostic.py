import pathlib,subprocess,time,json,xml.etree.ElementTree as E
out=pathlib.Path('apk-diagnostics');out.mkdir(exist_ok=True);meta=json.load(open('candidate/meta.json'));pkg=meta['packageName']
def adb(*args):return subprocess.run(['adb',*args],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120).stdout
print(adb('root'));adb('wait-for-device');adb('install','-r','-g','--abi','x86_64','candidate/'+meta['fileName']);adb('logcat','-c')
print(adb('shell','am','start','-W','-n',pkg+'/.MainActivity'),flush=True)
for i in range(8):
 time.sleep(2);adb('shell','uiautomator','dump','/sdcard/first-frame.xml');s=adb('shell','cat','/sdcard/first-frame.xml');(out/f'window-{i}.xml').write_text(s)
 (out/f'frame-{i}.png').write_bytes(subprocess.check_output(['adb','exec-out','screencap','-p']))
 print('FIRST_FRAME',i,'ready' if 'current-address-card' in s else s[:150],flush=True)
 if 'current-address-card' in s:break
pids=adb('shell','pidof',pkg).strip().split()
for pid in pids:
 if pid.isdigit():adb('shell','kill','-3',pid)
time.sleep(2)
(out/'logcat.txt').write_text(adb('logcat','-d','-v','threadtime'));(out/'activity.txt').write_text(adb('shell','dumpsys','activity','processes'));(out/'gfxinfo.txt').write_text(adb('shell','dumpsys','gfxinfo',pkg,'framestats'))
subprocess.run(['adb','pull','/data/anr',str(out/'anr')],check=False)
