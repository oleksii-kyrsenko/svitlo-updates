import io,json,re,urllib.request,zipfile
from pathlib import Path
from urllib.parse import urlparse
request=json.loads(Path('.channel/release-request.json').read_text())
url=request['artifactUrl']
parsed=urlparse(url)
assert parsed.scheme=='https' and (parsed.hostname.endswith('.blob.core.windows.net') or parsed.hostname.endswith('.actions.githubusercontent.com')),'Unexpected artifact host'
with urllib.request.urlopen(url,timeout=60) as response:
    data=response.read(64*1024*1024+1)
assert len(data)<=64*1024*1024,'Artifact too large'
allowed={'SHA256SUMS.txt','signature.txt','update.json','THIRD_PARTY_NOTICES.txt'}
with zipfile.ZipFile(io.BytesIO(data)) as archive:
    files=archive.infolist()
    assert len(files)<=6 and sum(item.file_size for item in files)<=160*1024*1024,'Unexpected artifact contents'
    for item in files:
        assert item.filename in allowed or re.fullmatch(r'svitlo-test-\d+\.apk',item.filename),'Unexpected artifact filename'
    Path('artifact').mkdir(exist_ok=True)
    for item in files:
        Path('artifact',item.filename).write_bytes(archive.read(item))
print('Downloaded APK artifact; request URL intentionally omitted from logs')
