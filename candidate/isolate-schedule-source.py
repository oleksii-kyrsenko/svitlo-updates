"""External test-emulator host isolation, not a change to the APK or TLS policy."""
import subprocess,pathlib
out=pathlib.Path('apk-diagnostics');out.mkdir(exist_ok=True)
def adb(*args):return subprocess.check_output(['adb',*args],text=True,stderr=subprocess.STDOUT)
hosts=['www.cherkasyoblenergo.com','cherkasyoblenergo.com','cabinet.cherkasyoblenergo.com']
data=adb('shell','cat','/system/etc/hosts')+'\n127.0.0.1 '+' '.join(hosts)+'\n::1 '+' '.join(hosts)+'\n'
p=out/'isolated-schedule-hosts';p.write_text(data);remote='/data/local/tmp/svitlo-visual-hosts';adb('push',str(p),remote);adb('shell','chmod','644',remote);adb('shell','chcon','u:object_r:system_file:s0',remote)
pids=['1']
for name in ['zygote64','zygote','netd']:
 r=subprocess.run(['adb','shell','pidof',name],stdout=subprocess.PIPE,text=True);pids += [p for p in r.stdout.split() if p.isdigit()]
for pid in dict.fromkeys(pids):adb('shell','nsenter','--mount=/proc/'+pid+'/ns/mnt','--','mount','--bind',remote,'/system/etc/hosts')
for host in hosts:
 r=subprocess.run(['adb','shell','ping','-c','1','-W','1',host],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True);assert '127.0.0.1' in r.stdout or '::1' in r.stdout,r.stdout
print('Schedule hosts isolated in the test emulator; cached fixture cannot be replaced by live publications')
