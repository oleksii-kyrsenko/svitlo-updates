import {readFile,writeFile,mkdir,rm} from 'node:fs/promises';
import {execFile} from 'node:child_process';import {promisify} from 'node:util';
import {createPublicKey,verify} from 'node:crypto';import {pathToFileURL} from 'node:url';
import {build,validateBundle,hash} from './build.mjs';import {mergeSnapshots,compactSnapshot,canonicalStreet} from './snapshots.mjs';
import {GROUPS,collectionPlan} from './collector-registry.mjs';
import {buildCityCoverage} from './build-v2.mjs';
import {readSourceSnapshots} from './publisher-snapshots.mjs';
import {legacyCompatibleBundles} from './legacy-compat.mjs';
const run=promisify(execFile);
export function prepareDtekSnapshot(previous,fresh){
 if(!fresh?.operatorId?.startsWith('dtek-'))return fresh;
 const key=r=>JSON.stringify([r.regionId,r.settlement,r.community,canonicalStreet(r.street)]);
 const legacy=new Map();
 for(const r of previous?.records||[]){if(r.officialCityId===r.settlement)legacy.set(key(r),r.officialCityId);}
 return {...fresh,records:fresh.records.map(r=>{
  // Retain the already shipped city selector only on its original street.
  // New streets use their own normalized street name, never another street's
  // city selector. Do not rewrite an unrelated operator/branch identity.
  const copy={...r};if(copy.street)copy.street=canonicalStreet(copy.street);if(copy.officialCityId===copy.settlement)delete copy.officialCityId;
  if(!copy.officialCityId&&legacy.has(key(copy)))copy.officialCityId=legacy.get(key(copy));
  return copy;
 })};
}
export function liveSnapshot(value,now=Date.now()){
 const copy={...value,records:value.records?.filter(r=>!Number.isFinite(r.expiresAt)||r.expiresAt>now)};
 return validateBundle(copy,now);
}
export function combineSnapshots(previous,collected,now=Date.now()){
 const result=new Map();for(const old of previous){try{const live=liveSnapshot(old,now);result.set(live.operatorId,live);}catch{}}
 const errors=[],withdrawnOperators=new Set();
 for(const raw of collected){let fresh=raw;try{
  fresh=prepareDtekSnapshot(result.get(raw?.operatorId),raw);
  const emptyObservation=fresh?.schemaVersion===1&&Array.isArray(fresh.records)&&fresh.records.length===0&&Array.isArray(fresh.observedHouses)&&fresh.observedHouses.length>0;
  if(emptyObservation){
   if(!/^[-a-z0-9]+$/.test(fresh.operatorId)||!Number.isFinite(fresh.generatedAt)||fresh.generatedAt>now||now-fresh.generatedAt>86400000||!Number.isFinite(fresh.expiresAt)||fresh.expiresAt<=now||fresh.expiresAt>fresh.generatedAt+86400000||fresh.observedHouses.length>100000)throw Error('invalid_empty_observation');
   for(const o of fresh.observedHouses)if(!/^UA-\d\d$/.test(o.regionId)||!['settlement','community','street','house'].every(k=>typeof o[k]==='string'&&o[k].length>0&&o[k].length<=500))throw Error('invalid_observed_house');
  }else validateBundle(fresh,now);
  const merged=compactSnapshot(mergeSnapshots(fresh.completeSnapshot?null:result.get(fresh.operatorId),fresh,now));
  if(emptyObservation&&!merged.records.length){result.delete(fresh.operatorId);withdrawnOperators.add(fresh.operatorId);continue;}
  validateBundle(merged,now);result.set(fresh.operatorId,merged);withdrawnOperators.delete(fresh.operatorId);
 }catch{errors.push({operatorId:fresh?.operatorId,error:'fresh_snapshot_invalid_previous_unexpired_preserved'});}}
 return {bundles:[...result.values()],errors,withdrawnOperators:[...withdrawnOperators]};
}
function checkedPrevious(envelope,version,key,now){
 const bytes=Buffer.from(envelope?.payload||'','base64');
 if(envelope?.schemaVersion!==version||envelope.keyId!=='coverage-v1'||bytes.length>2*1024*1024||!verify(null,bytes,key,Buffer.from(envelope.signature||'','base64')))throw Error('unverified_previous_coverage');
 const value=JSON.parse(bytes);
 if(value.schemaVersion!==version||value.minClientVersion!==version||!Number.isSafeInteger(value.revision)||value.revision<1||typeof value.enabled!=='boolean'||!Number.isFinite(value.generatedAt)||value.generatedAt>now||!Number.isFinite(value.expiresAt)||value.expiresAt<=value.generatedAt||value.expiresAt>value.generatedAt+86400000||!Array.isArray(value.bundles))throw Error('invalid_previous_coverage');
 return value;
}
export async function previousSnapshot(out,now,{publicKey}={}){
 const key=publicKey||createPublicKey(await readFile(new URL('./public.pem',import.meta.url)));
 let revision=1;const bundles=[];
 let legacyEnvelope=null;try{legacyEnvelope=JSON.parse(await readFile(out+'/manifest.json'));}catch(error){if(error.code!=='ENOENT')throw error;}
 if(legacyEnvelope){
  const old=checkedPrevious(legacyEnvelope,1,key,now);revision=old.revision+1;
  if(old.enabled)for(const e of old.bundles){try{if(!/^[a-f0-9]{64}$/.test(e.sha256)||e.url!=='https://raw.githubusercontent.com/oleksii-kyrsenko/svitlo-updates/main/dynamic-coverage/bundles/'+e.sha256+'.json')continue;const raw=await readFile(out+'/bundles/'+e.sha256+'.json');if(raw.length!==e.size||hash(raw)!==e.sha256)continue;const b=liveSnapshot(JSON.parse(raw),now);if(b.operatorId===e.operatorId&&b.expiresAt===e.expiresAt)bundles.push(b);}catch{}}
 }
 // Full source cache is authenticated by the v2 parent before any file is read.
 // Corruption stops publication; it must never look like an official withdrawal.
 let cityEnvelope=null;try{cityEnvelope=JSON.parse(await readFile(out+'/v2/manifest.json'));}catch(error){if(error.code!=='ENOENT')throw error;}
 if(cityEnvelope){
  const cityManifest=checkedPrevious(cityEnvelope,2,key,now);revision=Math.max(revision,cityManifest.revision+1);
  if(!cityManifest.enabled)return {revision,bundles:[],legacyBundles:[]};
  const full=await readSourceSnapshots(cityManifest,out+'/v2',now),fullIds=new Set(full.map(b=>b.operatorId));
  return {revision,bundles:[...bundles.filter(b=>!fullIds.has(b.operatorId)),...full],legacyBundles:bundles};
 }
 return {revision,bundles,legacyBundles:bundles};
}
export async function refresh(){
 const out='dynamic-coverage',startedAt=Date.now();await mkdir('coverage/staging',{recursive:true});await mkdir('coverage/cursors',{recursive:true});
 const previous=await previousSnapshot(out,startedAt),report={checkedAt:startedAt,errors:[],collections:[]};
 const all=Object.values(GROUPS).flat(),selected=process.env.COVERAGE_OPERATORS?process.env.COVERAGE_OPERATORS.split(',').filter(Boolean):all;
 if(selected.some(id=>!all.includes(id)))throw Error('unknown_requested_operator');
 const budget=Math.max(1,Math.min(40,Number(process.env.COVERAGE_ADDRESS_BUDGET||20))),streetBudget=Math.max(1,Math.min(30,Number(process.env.COVERAGE_STREET_BUDGET||8)));
 if(!Number.isInteger(budget)||!Number.isInteger(streetBudget))throw Error('invalid_budget');
 const cfg=JSON.parse(await readFile('coverage/sources.json')),geography=JSON.parse(await readFile('coverage/capital-geography.json'));
 const requestLimit=Number(process.env.COVERAGE_CITY_REQUEST_LIMIT||400);
 const commands=collectionPlan(cfg.operators,geography.cities,selected,{budget,streetBudget,requestLimit}),collected=[];let next=0;
 async function worker(){while(next<commands.length){const c=commands[next++];await rm(c.output,{force:true});let error=null;
  try{await run('python3',c.args,{timeout:c.fullCity?540000:240000,maxBuffer:1024*1024});collected.push(JSON.parse(await readFile(c.output)));}catch(e){error=e.killed?'collector_timeout':'collector_failed';report.errors.push({operatorId:c.operatorId,error});}
  let sidecar=null;try{sidecar=JSON.parse(await readFile(c.output+'.report.json'));}catch{}
  report.collections.push({operatorId:c.operatorId,targetCity:c.targetCity,cityCrawl:sidecar?.cityCrawl||sidecar?.traversal||null,status:error?'not_collected':'collected',records:sidecar?.records??sidecar?.recordCount??null,constraint:sidecar?.constraint||null,caseChecks:sidecar?.caseChecks?.length??sidecar?.sampleChecks?.length??sidecar?.addressChecks?.length??sidecar?.checks?.length??sidecar?.checkedAddresses??null});
 }}
 await Promise.all(Array.from({length:Math.min(4,commands.length)},worker));
 const now=Date.now(),combined=combineSnapshots(previous.bundles,collected,now);report.publicationCheckedAt=now;report.errors.push(...combined.errors);
 const writeReport=()=>writeFile('coverage/refresh-report.json',JSON.stringify(report,null,2)+'\n');
 if(!process.env.DYNAMIC_COVERAGE_KEY_FILE){report.signing='missing_key';await writeReport();throw Error('Signing secret unavailable; previous signed manifest preserved');}
 if(!combined.bundles.length&&!combined.withdrawnOperators.length){report.signing='no_valid_bundles_previous_manifest_preserved';await writeReport();throw Error('No valid source snapshots; previous signed manifest preserved');}
 const catalog={schemaVersion:1,generatedAt:now,expiresAt:now+86400000,operators:cfg.operators};
 let previousManifest=null;try{previousManifest=JSON.parse(await readFile(out+'/v2/manifest.json'));}catch(error){if(error.code!=='ENOENT')throw error;}
 const legacy=legacyCompatibleBundles(combined.bundles,previous.legacyBundles,now);report.legacyConstraints=legacy.constraints;
 report.publication=await build({catalog,bundles:legacy.bundles,revision:previous.revision,keyFile:process.env.DYNAMIC_COVERAGE_KEY_FILE,out,now,allowEmptyPublication:legacy.constraints.length>0||combined.withdrawnOperators.length>0});
 report.cityPublication=await buildCityCoverage({catalog,bundles:combined.bundles,revision:previous.revision,keyFile:process.env.DYNAMIC_COVERAGE_KEY_FILE,out:out+'/v2',geography,now,previousManifest,allowEmptyPublication:combined.withdrawnOperators.length>0});
 await writeReport();console.log(JSON.stringify({legacy:report.publication,cities:report.cityPublication}));return report;
}
if(import.meta.url===pathToFileURL(process.argv[1]||'').href)await refresh();
