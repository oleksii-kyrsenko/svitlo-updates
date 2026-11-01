"""One request per host per second across local collector processes."""
import fcntl,hashlib,tempfile,time,urllib.parse
from pathlib import Path

def throttle(url):
 host=urllib.parse.urlsplit(url).hostname
 if not host:raise ValueError('missing_source_host')
 path=Path(tempfile.gettempdir())/('koly-source-rate-'+hashlib.sha256(host.encode()).hexdigest()[:24])
 with path.open('a+') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX);lock.seek(0)
  try:previous=float(lock.read())
  except ValueError:previous=0
  delay=previous+1.05-time.monotonic()
  if delay>0:time.sleep(min(delay,1.05))
  lock.seek(0);lock.truncate();lock.write(str(time.monotonic()));lock.flush()
