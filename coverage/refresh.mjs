import {readFile,writeFile,mkdir} from 'node:fs/promises';import {execFileSync} from 'node:child_process';import {build,validateBundle} from './build.mjs';
import {mergeSnapshots} from './snapshots.mjs';
const now=Date.now(),out='dynamic-coverage';await mkdir('coverage/staging',{recursive:true});const report={checkedAt:now,errors:[]};
const previous=[];let revision=1;
try{const env=JSON.parse(await readFile(out+'/manifest.json'));const old=JSON.parse(Buffer.from(env.payload,'base64'));revision=old.revision+1;for(const e of old.bundles||[]){try{const b=JSON.parse(await readFile(out+'/bundles/'+e.sha256+'.json'));validateBundle(b,now);previous.push(b);}catch{}}}catch{}
let collected=false;
try{execFileSync('python3',['coverage/collect-asd.py','--output','coverage/staging/lviv.json','--street-limit',String(Number(process.env.COVERAGE_STREET_BUDGET||8)),'--state','coverage/crawl-state.json'],{stdio:'inherit',timeout:600000});collected=true;}catch{report.errors.push({operatorId:'lviv',error:'collector_failed'});}
const bundles=[...previous];if(collected){const fresh=JSON.parse(await readFile('coverage/staging/lviv.json'));const merged=mergeSnapshots(previous.find(b=>b.operatorId==='lviv'),fresh,now);const i=bundles.findIndex(b=>b.operatorId==='lviv');if(i>=0)bundles.splice(i,1);if(merged.records.length){validateBundle(merged,now);bundles.push(merged);} }
if(!process.env.DYNAMIC_COVERAGE_KEY_FILE){report.signing='missing_key';await writeFile('coverage/refresh-report.json',JSON.stringify(report,null,2)+'\n');throw Error('Signing secret unavailable; previous signed manifest preserved');}
const cfg=JSON.parse(await readFile('coverage/sources.json'));const catalog={schemaVersion:1,generatedAt:now,expiresAt:now+86400000,operators:cfg.operators};
report.publication=await build({catalog,bundles,revision,keyFile:process.env.DYNAMIC_COVERAGE_KEY_FILE,out,now});await writeFile('coverage/refresh-report.json',JSON.stringify(report,null,2)+'\n');console.log(report.publication);
