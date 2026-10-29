"""Disable only live directory observations, preserving other public sources."""
import json,pathlib,time

def disable(root):
 root=pathlib.Path(root);path=root/'manifest.json';manifest=json.loads(path.read_text())
 manifest['records']=[r for r in manifest.get('records',[]) if r.get('evidenceType')!='address-directory']
 manifest['generatedAt']=int(time.time()*1000)
 path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
 (root/'directory'/'sources.json').write_text('[]\n')
 return len(manifest['records'])
if __name__=='__main__':print('Other public records retained:',disable(pathlib.Path(__file__).resolve().parents[1]))
