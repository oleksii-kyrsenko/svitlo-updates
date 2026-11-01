"""Maintain one operational task; avoid one issue per failed HTTP request."""
import json,subprocess,tempfile
from pathlib import Path
report=json.loads(Path('coverage/report.json').read_text());problems=[r for r in report['operators'] if r.get('consecutiveFailures',0)>=2]
collection=None
try:
 candidate=json.loads(Path('coverage/refresh-report.json').read_text())
 if candidate.get('checkedAt',0)>=report['checkedAt']:collection=candidate
except (FileNotFoundError,ValueError):pass
collection_errors={r.get('operatorId') for r in (collection or {}).get('errors',[])}
collection_problems=[r for r in (collection or {}).get('collections',[]) if r.get('status')!='collected' or not r.get('records') or r.get('operatorId') in collection_errors]
registry=report.get('registry',{});review=registry.get('reviewRequired',False)
if not problems and not review and not collection_problems:raise SystemExit(0)
title='Coverage source monitoring: investigation required'
issues=json.loads(subprocess.check_output(['gh','issue','list','--state','open','--search',title+' in:title','--json','number,title']))
existing=next((x for x in issues if x['title']==title),None)
lines=['Automated source health report. Page availability does not establish address coverage.','', 'Repeated failures:']
lines.extend(f"- {r['operatorId']}: {r['status']} ({r['consecutiveFailures']} checks), {r['sourceUrl']}" for r in problems)
if collection_problems:
 lines.extend(['','Current normalized collection gaps (a reachable page does not resolve an address):'])
 lines.extend(f"- {r['operatorId']}: {r.get('constraint') or r.get('status')}; records={r.get('records')}; source checks={r.get('caseChecks')}" for r in collection_problems)
 lines.extend(['','Fresh collection checked at: '+str(collection['checkedAt'])+'. Unexpired retained bundles do not establish a successful fresh collection.'])
if review:lines.extend(['','Regulator register links changed or need initial review. Compare legal identifiers and license status before catalog changes.',str(registry)])
lines.extend(['','Agent tasks: investigate official source; discover local/public alternatives; verify geography and dated address evidence; reproduce fix; run independent regression checks.','No production queue should be inferred from this health report.'])
with tempfile.NamedTemporaryFile('w',suffix='.md') as f:
 f.write('\n'.join(lines));f.flush()
 command=['gh','issue','edit',str(existing['number']),'--body-file',f.name] if existing else ['gh','issue','create','--title',title,'--body-file',f.name]
 subprocess.run(command,check=True)
