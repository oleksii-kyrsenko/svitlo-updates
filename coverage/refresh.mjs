import {readFile,writeFile,mkdir,rm} from 'node:fs/promises';
import {execFile} from 'node:child_process';import {promisify} from 'node:util';
import {createPublicKey,verify} from 'node:crypto';import {pathToFileURL} from 'node:url';
import {build,validateBundle,hash} from './build.mjs';import {mergeSnapshots,compactSnapshot} from './snapshots.mjs';
import {GROUPS,collectorCommand} from './collector-registry.mjs';
const run=promisify(execFile);
export function liveSnapshot(value,now=Date.now()){
 const copy={...value,records:value.records?.filter(r=>!Number.isFinite(r.expiresAt)||r.expiresAt>now)};
 return validateBundle(copy,now);
}
export function combineSnapshots(previous,collected,now=Date.now()){
 const result=new Map();for(const old of previous){try{const live=liveSnapshot(old,now);result.set(live.operatorId,live);}catch{}}
 const errors=[];
 for(const fresh of collected){try{
  validateBundle(fresh,now);
  const merged=compactSnapshot(mergeSnapshots(fresh.completeSnapshot?null:result.get(fresh.operatorId),fresh,now));validateBundle(merged,now);result.set(fresh.operatorId,merged);
 }catch{errors.push({operatorId:fresh?.operatorId,error:'fresh_snapshot_invalid_previous_unexpired_preserved'});}}
 return {bundles:[...result.values()],errors};
}
async function previousSnapshot(out,now){
 let revision=1;const bundles=[];
 try{
  const env=JSON.parse(await readFile(out+'/manifest.json'));const bytes=Buffer.from(env.payload,'base64');
  const key=createPublicKey(await readFile(new URL('./public.pem',import.meta.url)));
  if(env.schemaVersion!==1||env.keyId!=='coverage-v1'||!verify(null,bytes,key,Buffer.from(env.signature,'base64')))throw Error('unverified_previous');
  const old=JSON.parse(bytes);if(!Number.isSafeInteger(old.revision)||old.revision<1)throw Error('invalid_previous_revision');revision=old.revision+1;
  for(const e of old.bundles||[]){try{if(!/^[a-f0-9]{64}$/.test(e.sha256))continue;const raw=await readFile(out+'/bundles/'+e.sha256+'.json');if(raw.length!==e.size||hash(raw)!==e.sha256)continue;const b=liveSnapshot(JSON.parse(raw),now);if(b.operatorId===e.operatorId)bundles.push(b);}catch{}}
 }catch{}
 return {revision,bundles};
}
export async function refresh(){
 const out='dynamic-coverage',startedAt=Date.now();await mkdir('coverage/staging',{recursive:true});await mkdir('coverage/cursors',{recursive:true});
 const previous=await previousSnapshot(out,startedAt),report={checkedAt:startedAt,errors:[],collections:[]};
 const all=Object.values(GROUPS).flat(),selected=process.env.COVERAGE_OPERATORS?process.env.COVERAGE_OPERATORS.split(',').filter(Boolean):all;
 if(selected.some(id=>!all.includes(id)))throw Error('unknown_requested_operator');
 const budget=Math.max(1,Math.min(40,Number(process.env.COVERAGE_ADDRESS_BUDGET||20))),streetBudget=Math.max(1,Math.min(30,Number(process.env.COVERAGE_STREET_BUDGET||8)));
 if(!Number.isInteger(budget)||!Number.isInteger(streetBudget))throw Error('invalid_budget');
 const commands=selected.map(id=>collectorCommand(id,{budget,streetBudget})),collected=[];let next=0;
 async function worker(){while(next<commands.length){const c=commands[next++];await rm(c.output,{force:true});let error=null;
  try{await run('python3',c.args,{timeout:240000,maxBuffer:1024*1024});collected.push(JSON.parse(await readFile(c.output)));}catch(e){error=e.killed?'collector_timeout':'collector_failed';report.errors.push({operatorId:c.operatorId,error});}
  let sidecar=null;try{sidecar=JSON.parse(await readFile(c.output+'.report.json'));}catch{}
  report.collections.push({operatorId:c.operatorId,status:error?'not_collected':'collected',records:sidecar?.records??sidecar?.recordCount??null,constraint:sidecar?.constraint||null,caseChecks:sidecar?.caseChecks?.length??sidecar?.sampleChecks?.length??sidecar?.addressChecks?.length??sidecar?.checks?.length??sidecar?.checkedAddresses??null});
 }}
 await Promise.all(Array.from({length:Math.min(4,commands.length)},worker));
 const now=Date.now(),combined=combineSnapshots(previous.bundles,collected,now);report.publicationCheckedAt=now;report.errors.push(...combined.errors);
 const writeReport=()=>writeFile('coverage/refresh-report.json',JSON.stringify(report,null,2)+'\n');
 if(!process.env.DYNAMIC_COVERAGE_KEY_FILE){report.signing='missing_key';await writeReport();throw Error('Signing secret unavailable; previous signed manifest preserved');}
 if(!combined.bundles.length){report.signing='no_valid_bundles_previous_manifest_preserved';await writeReport();throw Error('No valid source snapshots; previous signed manifest preserved');}
 const cfg=JSON.parse(await readFile('coverage/sources.json')),catalog={schemaVersion:1,generatedAt:now,expiresAt:now+86400000,operators:cfg.operators};
 report.publication=await build({catalog,bundles:combined.bundles,revision:previous.revision,keyFile:process.env.DYNAMIC_COVERAGE_KEY_FILE,out,now});await writeReport();console.log(JSON.stringify(report.publication));return report;
}
if(import.meta.url===pathToFileURL(process.argv[1]||'').href)await refresh();
