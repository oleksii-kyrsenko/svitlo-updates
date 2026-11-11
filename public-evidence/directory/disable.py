"""Disable only live directory observations, preserving other public sources."""
import json,pathlib,time,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from manifest_io import serialize_manifest,write_manifest

def disable(root):
 root=pathlib.Path(root);path=root/'manifest.json';manifest=json.loads(path.read_text())
 manifest['records']=[r for r in manifest.get('records',[]) if r.get('evidenceType')!='address-directory']
 manifest['generatedAt']=int(time.time()*1000)
 serialize_manifest(manifest)
 (root/'directory'/'sources.json').write_text('[]\n')
 write_manifest(path,manifest)
 return len(manifest['records'])
if __name__=='__main__':print('Other public records retained:',disable(pathlib.Path(__file__).resolve().parents[1]))
