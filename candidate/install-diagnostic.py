"""Install the exact independently verified APK for native diagnostic cases."""
import json,subprocess,pathlib
meta=json.loads(pathlib.Path('candidate/meta.json').read_text())
assert meta['versionCode']==88
subprocess.run(['adb','install','-r','-g','--abi','x86_64','candidate/'+meta['fileName']],check=True)
