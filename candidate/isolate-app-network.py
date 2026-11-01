"""External root-emulator isolation: reject only this app UID's outbound packets.
The APK, system DNS/TLS settings and shell/adb networking remain unchanged.
"""
import json,pathlib,subprocess
out=pathlib.Path('apk-diagnostics');out.mkdir(exist_ok=True)
meta=json.loads(pathlib.Path('candidate/meta.json').read_text());pkg=meta['packageName']
def adb(*args):return subprocess.check_output(['adb',*args],text=True,stderr=subprocess.STDOUT,timeout=60)
assert 'uid=0' in adb('shell','id'),'Root emulator required for app-only network isolation'
uid=adb('shell','stat','-c','%u','/data/data/'+pkg).strip()
assert uid.isdigit() and int(uid)>=10000,('Unexpected application UID',uid)
report={'packageName':pkg,'appUid':int(uid),'chains':{}}
try:
 for binary in ['iptables','ip6tables']:
  # Insert before any broader ACCEPT rules; keep adb/shell/system UIDs untouched.
  args=['-w','10','-I','OUTPUT','1','-m','owner','--uid-owner',uid,'-j','REJECT']
  adb('shell',binary,*args)
  adb('shell',binary,'-w','10','-C','OUTPUT','-m','owner','--uid-owner',uid,'-j','REJECT')
  rules=adb('shell',binary,'-w','10','-S','OUTPUT')
  (out/(binary+'-app-network-rules.txt')).write_text(rules)
  assert any('--uid-owner '+uid in rule and '-j REJECT' in rule for rule in rules.splitlines()),rules
  report['chains'][binary]={'outputOwnerRejectVerified':True}
 report['allPassed']=len(report['chains'])==2
finally:
 (out/'app-network-isolation.json').write_text(json.dumps(report,indent=2)+'\n')
assert report.get('allPassed'),report
print('App UID outbound traffic rejected in IPv4 and IPv6; adb and shell networking retained',flush=True)
