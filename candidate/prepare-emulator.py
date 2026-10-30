"""Retry only adb initialization before any product installation/test."""
import subprocess,time
for attempt in range(6):
 subprocess.run(['adb','wait-for-device'],check=True,timeout=90)
 p=subprocess.run(['adb','root'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=30)
 if p.returncode==0:
  subprocess.run(['adb','wait-for-device'],check=True,timeout=90)
  q=subprocess.run(['adb','shell','id'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=30)
  if q.returncode==0 and 'uid=0' in q.stdout:break
 time.sleep(2)
else:raise RuntimeError('Emulator adb root initialization failed before testing')
print('Emulator root connection ready')
