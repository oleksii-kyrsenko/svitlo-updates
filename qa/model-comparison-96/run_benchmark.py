import json,pathlib,urllib.request,time,hashlib,subprocess,os,sys,tarfile,signal
from benchmark_core import infer
ROOT=pathlib.Path(__file__).resolve().parent
model=sys.argv[1];shard=int(sys.argv[2]);shards=int(sys.argv[3]);out=pathlib.Path(os.environ.get('BENCH_OUTPUT','results'));out.mkdir(exist_ok=True)
locks=json.loads((ROOT/'locks.json').read_text());lock=locks[model];work=pathlib.Path(os.environ.get('RUNNER_TEMP','/tmp'))/'svitlo-model-bench';work.mkdir(exist_ok=True)
def download(url,path,sha):
 if path.is_file() and hashlib.file_digest(path.open('rb'),'sha256').hexdigest()==sha:return
 print('downloading',path.name,flush=True)
 for attempt in range(3):
  try:
   with urllib.request.urlopen(url,timeout=180) as r,path.open('wb') as f:
    while chunk:=r.read(8*1024*1024):f.write(chunk)
   break
  except Exception:
   if attempt==2:raise
   time.sleep(5)
 digest=hashlib.file_digest(path.open('rb'),'sha256').hexdigest()
 if digest!=sha:raise ValueError('SHA256 mismatch')
weights=work/(model+'.gguf');download(lock['url'],weights,lock['sha256'])
runtime=work/'runtime.tar.gz';download(locks['runtime']['url'],runtime,locks['runtime']['sha256'])
with tarfile.open(runtime) as t:
 for m in t.getmembers():
  if m.name.startswith('/') or '..' in pathlib.PurePosixPath(m.name).parts:raise ValueError('unsafe archive')
 t.extractall(work,filter='data')
binary=next(work.rglob('llama-server'));binary.chmod(0o755)
command=[str(binary),'-m',str(weights),'--host','127.0.0.1','--port','8767','-c','6144','-t','4','--threads-batch','4','-np','1','--reasoning-budget','192','--reasoning-format','deepseek']
log=(out/'server.log').open('w');proc=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
try:
 for _ in range(180):
  if proc.poll() is not None:raise RuntimeError('server exited')
  try:
   with urllib.request.urlopen('http://127.0.0.1:8767/health',timeout=2) as r:
    if r.status==200:break
  except:pass
  time.sleep(1)
 else:raise TimeoutError('server health')
 allcases=json.loads((ROOT/'inputs.json').read_text())['cases'];cases=[c for i,c in enumerate(allcases) if i%shards==shard]
 manifest={'model':model,'modelLock':lock,'runtimeLock':locks['runtime'],'shard':shard,'shards':shards,'threads':4,'context':6144,'reasoningBudget':192,'maxTokens':512,'temperature':0,'seed':42,'caseCount':len(cases),'command':command,'platform':subprocess.check_output(['uname','-a'],text=True).strip(),'cpu':subprocess.check_output(['lscpu'],text=True),'inputsSha256':hashlib.file_digest((ROOT/'inputs.json').open('rb'),'sha256').hexdigest()};(out/'manifest.json').write_text(json.dumps(manifest,indent=2))
 for c in cases:
  t=time.monotonic();row={'id':c['id'],'kyivControl':c['kyivControl'],'model':model,'inputSha256':c['inputSha256']}
  try:row.update(infer(c))
  except Exception as e:row.update({'error':type(e).__name__+': '+str(e),'seconds':round(time.monotonic()-t,3)})
  (out/(c['id']+'.json')).write_text(json.dumps(row,ensure_ascii=False,indent=2)+'\n');print(c['id'],round(row['seconds'],1),row.get('parsed',{}).get('status'),row.get('parsed',{}).get('queue'),row.get('error',''),flush=True)
finally:
 proc.terminate()
 try:proc.wait(timeout=15)
 except:proc.kill()
