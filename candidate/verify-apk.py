"""Verify a distributed binary without checking out application sources."""
import pathlib,json,hashlib,subprocess,re,os
root=pathlib.Path('candidate');meta=json.loads((root/'meta.json').read_text())
apk=root/meta['fileName'];data=apk.read_bytes()
assert len(data)==meta['size'] and hashlib.sha256(data).hexdigest()==meta['sha256']
tools=sorted((pathlib.Path(os.environ['ANDROID_HOME'])/'build-tools').glob('*/apksigner'))
assert tools
signer=tools[-1]
signature=subprocess.check_output([str(signer),'verify','--verbose','--print-certs',str(apk)],text=True)
assert set(re.findall(r'certificate SHA-256 digest:\s*([a-fA-F0-9]{64})',signature))=={'fac61745dc0903786fb9ede62a962b399f7348f0bb6f899b8332667591033b9c'}
badging=subprocess.check_output([str(signer.with_name('aapt')),'dump','badging',str(apk)],text=True)
assert f"name='{meta['packageName']}'" in badging
assert f"versionCode='{meta['versionCode']}'" in badging and f"versionName='{meta['version']}'" in badging
(root/'signature.txt').write_text(signature)
print('Verified APK bytes, package, version and pinned signing certificate')
