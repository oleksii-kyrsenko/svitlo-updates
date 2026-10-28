"""One-command rollback; commit/push the two changed control files afterwards."""
import json,pathlib
root=pathlib.Path(__file__).parent
for name in ['sources.json','manifest.json']:
 p=root/name;value=json.loads(p.read_text());value['enabled']=False;p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
print('Disabled public suggestions and future publication. Official lookup and manual queues are untouched. Commit and push sources.json and manifest.json to main.')
