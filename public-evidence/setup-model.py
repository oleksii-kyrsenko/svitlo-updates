import hashlib,json,os,pathlib,tarfile,urllib.request
root=pathlib.Path(__file__).parent;lock=json.loads((root/'model-lock.json').read_text());cache=root/'.cache';cache.mkdir(exist_ok=True)
def download(url,path,digest):
 if not path.exists() or hashlib.file_digest(path.open('rb'),'sha256').hexdigest()!=digest:
  part=path.with_suffix('.part');urllib.request.urlretrieve(url,part)
  assert hashlib.file_digest(part.open('rb'),'sha256').hexdigest()==digest
  part.replace(path)
download(lock['runtimeUrl'],cache/'runtime.tar.gz',lock['runtimeSha256'])
with tarfile.open(cache/'runtime.tar.gz') as t:t.extractall(cache/'runtime',filter='data')
download(lock['modelUrl'],cache/'model.gguf',lock['modelSha256'])
assert (cache/'model.gguf').stat().st_size==lock['modelBytes']
if os.environ.get('GITHUB_ENV'):
 with open(os.environ['GITHUB_ENV'],'a') as f:f.write('EVIDENCE_SERVER='+str((cache/'runtime'/lock['runtimeDirectory']/'llama-server').resolve())+'\nEVIDENCE_MODEL='+str((cache/'model.gguf').resolve())+'\n')
print('Pinned runtime and open model verified; no inference API used')
