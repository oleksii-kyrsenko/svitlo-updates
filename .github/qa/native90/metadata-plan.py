"""Require the real sealed candidate metadata before any emulator is started."""
import importlib.util,json,os,pathlib
root=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('native90_contract',root/'contract.py');contract=importlib.util.module_from_spec(spec);spec.loader.exec_module(contract)
if not(root/'meta.json').is_file():raise ValueError('Seal candidate90 and add its actual meta.json before dispatch; no invented hash is accepted')
candidate=json.loads((root/'meta.json').read_text());baseline=json.loads((root/'baseline-89.json').read_text());contract.validate_metadata(candidate,baseline)
fields={'apkUrl':contract.candidate_url(candidate),'apkSha256':candidate['sha256'],'apkSize':candidate['size'],'versionCode':candidate['versionCode'],'version':candidate['version'],'sourceCommit':candidate['sourceCommit']}
with open(os.environ['GITHUB_OUTPUT'],'a')as out:
 for key,value in fields.items():out.write(key+'='+str(value)+'\n')
print(json.dumps(fields))
