"""One-command rollback; commit/push the two changed control files afterwards."""
import json,pathlib
from manifest_io import serialize_manifest,write_manifest

def disable(root):
 root=pathlib.Path(root);source=root/'sources.json';manifest=root/'manifest.json'
 config=json.loads(source.read_text());value=json.loads(manifest.read_text());config['enabled']=False;value['enabled']=False
 serialize_manifest(value)
 source.write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n')
 write_manifest(manifest,value)

if __name__=='__main__':
 disable(pathlib.Path(__file__).parent)
 print('Disabled public suggestions and future publication. Official lookup and manual queues are untouched. Commit and push sources.json and manifest.json to main.')
