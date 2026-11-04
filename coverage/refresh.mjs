import {readFile,writeFile,mkdir,rm,stat} from 'node:fs/promises';
import {execFile} from 'node:child_process';import {promisify} from 'node:util';
import {createPublicKey,verify} from 'node:crypto';import {pathToFileURL} from 'node:url';
import {build,validateBundle,hash} from './build.mjs';import {mergeSnapshots,compactSnapshot,canonicalStreet} from './snapshots.mjs';
import {GROUPS,collectionPlan} from './collector-registry.mjs';
import {buildCityCoverage} from './build-v2.mjs';
import {readSourceSnapshots,validatePublisherSnapshot,MAX_SOURCE_SNAPSHOT} from './publisher-snapshots.mjs';
import {legacyCompatibleBundles} from './legacy-compat.mjs';
const run=promisify(execFile);
async function readCollectorJson(file){
 if((await stat(file)).size>MAX_SOURCE_SNAPSHOT)throw Error('collector_output_too_large');
 return JSON.parse(await readFile(file));
}
function checkpointSnapshot(raw,command,{startedAt,now,operator,target,partial}){
 // Only the resumable public city forms currently write atomic, timestamped
 // per-street checkpoints. Other collectors keep their ordinary failure path.
 const sameGeography=r=>r.regionId===target.regionId&&r.settlement===target.settlement&&r.community===target.community;
 const observedKeys=new Set(['regionId','settlement','community','street','house','providerStreetId','checkedAt','expiresAt']);
 const host=url=>{const value=new URL(url);if(value.protocol!=='https:'||value.username||value.password||value.port&&value.port!=='443')throw Error('invalid_checkpoint_source');return value.hostname.replace(/^www\./,'');};
 if(!operator||operator.id!==command.operatorId||!target||target.settlement!==command.targetCity||!operator.regionIds.includes(target.regionId)||raw?.operatorId!==command.operatorId||raw.schemaVersion!==1||!Number.isFinite(raw.generatedAt)||raw.generatedAt<startedAt||raw.generatedAt>now||!Number.isFinite(raw.expiresAt)||raw.expiresAt<=now||raw.expiresAt>raw.generatedAt+86400000||!Array.isArray(raw.records)||!Array.isArray(raw.observedHouses)||raw.observedHouses.length>100000||raw.completeSnapshot||!Array.isArray(raw.completedStreetIds)||raw.completedStreetIds.some(id=>typeof id!=='string'||!id.length||id.length>150))throw Error('invalid_collector_checkpoint');
 for(const r of raw.records)if(!sameGeography(r)||r.scope!=='house'||r.checkedAt<startedAt||r.checkedAt>raw.generatedAt||host(r.sourceUrl)!==host(operator.sourceUrl))throw Error('invalid_checkpoint_record');
 for(const o of raw.observedHouses)if(!o||Object.keys(o).some(k=>!observedKeys.has(k))||!sameGeography(o)||!['street','house'].every(k=>typeof o[k]==='string'&&o[k].length>0&&o[k].length<=(k==='house'?30:500))||o.providerStreetId!==undefined&&(typeof o.providerStreetId!=='string'||!o.providerStreetId.length||o.providerStreetId.length>150)||!Number.isFinite(o.checkedAt)||o.checkedAt<startedAt||o.checkedAt>raw.generatedAt||!Number.isFinite(o.expiresAt)||o.expiresAt<=now||o.expiresAt>o.checkedAt+86400000||o.expiresAt>raw.expiresAt)throw Error('invalid_checkpoint_observation');
 // An interrupted read proves its explicit houses, not absence elsewhere.
 // Never infer a withdrawal from a partially completed operator/street crawl.
 const snapshot={schemaVersion:1,operatorId:raw.operatorId,generatedAt:raw.generatedAt,expiresAt:raw.expiresAt,records:raw.records,observedHouses:raw.observedHouses,completedStreetIds:partial?[]:raw.completedStreetIds};
 const checked=combineSnapshots([],[snapshot],now);
 if(checked.errors.length||!checked.sourceSnapshots.length)throw Error('invalid_collector_checkpoint');
 return snapshot;
}
export async function collectSourceCommand(command,{runner=run,clock=Date.now,operator,target}={}){
 const checkpointed=command.fullCity===true&&command.args[0]==='coverage/collect-city-forms.py'&&['kirovohrad','volyn'].includes(command.operatorId);
 const stateIndex=command.args.indexOf('--state'),stateFile=checkpointed&&stateIndex>=0?command.args[stateIndex+1]:null;
 let oldCursor=null;if(stateFile){try{oldCursor=await readFile(stateFile);}catch(error){if(error.code!=='ENOENT')throw error;}}
 const rollbackCursor=stateFile?async()=>{if(oldCursor===null)await rm(stateFile,{force:true});else await writeFile(stateFile,oldCursor);}:null;
 // Removing both files prevents an earlier invocation's packet or sidecar
 // from being mistaken for progress by a collector which failed immediately.
 await rm(command.output,{force:true});await rm(command.output+'.report.json',{force:true});
 const startedAt=clock();let error=null,snapshot=null,checkpointRejected=false;
 try{await runner('python3',command.args,{timeout:command.fullCity?540000:240000,maxBuffer:1024*1024});}catch(cause){error=cause.killed?'collector_timeout':'collector_failed';}
 try{
  if(error&&!checkpointed)throw Error('collector_failed_without_checkpoint');
  const raw=await readCollectorJson(command.output);
  snapshot=checkpointed?checkpointSnapshot(raw,command,{startedAt,now:clock(),operator,target,partial:Boolean(error)}):raw;
 }catch{checkpointRejected=Boolean(error&&checkpointed);error=error||'collector_output_invalid';if(rollbackCursor)await rollbackCursor();}
 let sidecar=null;try{sidecar=await readCollectorJson(command.output+'.report.json');}catch{}
 return {snapshot,error,checkpointRecovered:Boolean(snapshot&&error),checkpointRejected,rollbackCursor,
  collection:{operatorId:command.operatorId,targetCity:command.targetCity,cityCrawl:sidecar?.cityCrawl||sidecar?.traversal||null,status:snapshot?(error?'collected_checkpoint':'collected'):'not_collected',records:snapshot?.records?.length??sidecar?.records??sidecar?.recordCount??null,constraint:sidecar?.constraint||null,caseChecks:sidecar?.caseChecks?.length??sidecar?.sampleChecks?.length??sidecar?.addressChecks?.length??sidecar?.checks?.length??sidecar?.checkedAddresses??null}};
}
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
 const copy={...value,records:value.records?.filter(r=>!Number.isFinite(r.expiresAt)||r.expiresAt>now),negativeHouseWatermarks:(value.negativeHouseWatermarks||[]).filter(w=>w.expiresAt>now)};
 return validatePublisherSnapshot(copy,now);
}
export function combineSnapshots(previous,collected,now=Date.now()){
 const result=new Map();for(const old of previous){try{const live=liveSnapshot(old,now);result.set(live.operatorId,live);}catch{}}
 const errors=[];
 for(const raw of collected){let fresh=raw;try{
  fresh=prepareDtekSnapshot(result.get(raw?.operatorId),raw);
  const emptyObservation=fresh?.schemaVersion===1&&Array.isArray(fresh.records)&&fresh.records.length===0&&Array.isArray(fresh.observedHouses)&&fresh.observedHouses.length>0;
  if(emptyObservation){
   if(!/^[-a-z0-9]+$/.test(fresh.operatorId)||!Number.isFinite(fresh.generatedAt)||fresh.generatedAt>now||now-fresh.generatedAt>86400000||!Number.isFinite(fresh.expiresAt)||fresh.expiresAt<=now||fresh.expiresAt>fresh.generatedAt+86400000||fresh.observedHouses.length>100000)throw Error('invalid_empty_observation');
   for(const o of fresh.observedHouses)if(!/^UA-\d\d$/.test(o.regionId)||!['settlement','community','street','house'].every(k=>typeof o[k]==='string'&&o[k].length>0&&o[k].length<=500))throw Error('invalid_observed_house');
  }else validateBundle(fresh,now);
  const merged=compactSnapshot(mergeSnapshots(result.get(fresh.operatorId),fresh,now));
  validatePublisherSnapshot(merged,now);result.set(fresh.operatorId,merged);
 }catch{errors.push({operatorId:fresh?.operatorId,error:'fresh_snapshot_invalid_previous_unexpired_preserved'});}}
 const sourceSnapshots=[...result.values()];
 const bundles=sourceSnapshots.filter(b=>b.records.length).map(b=>({schemaVersion:1,operatorId:b.operatorId,generatedAt:b.generatedAt,expiresAt:b.expiresAt,records:b.records}));
 return {bundles,sourceSnapshots,errors,withdrawnOperators:sourceSnapshots.filter(b=>!b.records.length).map(b=>b.operatorId)};
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
  const full=await readSourceSnapshots(cityManifest,out+'/v2',now);
  // A newer legacy publication can coexist with an older full source cache
  // after a compatible bot update. Merge positive facts by observation time;
  // the partial legacy view must never withdraw unrepresented full-city rows.
  const views=bundles.map(b=>({schemaVersion:1,operatorId:b.operatorId,generatedAt:b.generatedAt,expiresAt:b.expiresAt,records:b.records}));
  const merged=combineSnapshots(full,views,now);if(merged.errors.length)throw Error('previous_source_views_cannot_be_merged');
  return {revision,bundles:merged.sourceSnapshots,legacyBundles:bundles};
 }
 return {revision,bundles,legacyBundles:bundles};
}
export async function refresh({runner=run,clock=Date.now}={}){
 const out='dynamic-coverage',startedAt=clock();await mkdir('coverage/staging',{recursive:true});await mkdir('coverage/cursors',{recursive:true});
 const previous=await previousSnapshot(out,startedAt),report={checkedAt:startedAt,errors:[],collections:[]};
 const all=Object.values(GROUPS).flat(),selected=process.env.COVERAGE_OPERATORS?process.env.COVERAGE_OPERATORS.split(',').filter(Boolean):all;
 if(selected.some(id=>!all.includes(id)))throw Error('unknown_requested_operator');
 const budget=Math.max(1,Math.min(40,Number(process.env.COVERAGE_ADDRESS_BUDGET||20))),streetBudget=Math.max(1,Math.min(30,Number(process.env.COVERAGE_STREET_BUDGET||8)));
 if(!Number.isInteger(budget)||!Number.isInteger(streetBudget))throw Error('invalid_budget');
 const cfg=JSON.parse(await readFile('coverage/sources.json')),geography=JSON.parse(await readFile('coverage/capital-geography.json'));
 const requestLimit=Number(process.env.COVERAGE_CITY_REQUEST_LIMIT||400);
 const mode=process.env.COVERAGE_COLLECTION_MODE||'capital';if(!['capital','legacy'].includes(mode))throw Error('unknown_collection_mode');report.collectionMode=mode;
 const commands=collectionPlan(cfg.operators,geography.cities,selected,{budget,streetBudget,requestLimit,capitalPriority:mode==='capital'}),collected=[],cursorRollbacks=[];let next=0,published=false;
 try{
 async function worker(){while(next<commands.length){
  const c=commands[next++],operator=cfg.operators.find(o=>o.id===c.operatorId),targets=geography.cities.filter(g=>operator.regionIds.includes(g.regionId)&&g.settlement===c.targetCity);
  const result=await collectSourceCommand(c,{runner,clock,operator,target:targets.length===1?targets[0]:null});
  if(result.rollbackCursor)cursorRollbacks.push(result.rollbackCursor);
  if(result.snapshot)collected.push(result.snapshot);
  if(result.error)report.errors.push({operatorId:c.operatorId,error:result.error,...(result.checkpointRecovered?{checkpointRecovered:true}:{}),...(result.checkpointRejected?{checkpointRejected:true}:{})});
  report.collections.push(result.collection);
 }}
 // Finish all active collectors before restoring cursors after an I/O failure;
 // otherwise a still-running worker could overwrite the restored state.
 const workers=await Promise.allSettled(Array.from({length:Math.min(4,commands.length)},worker));
 const failed=workers.find(result=>result.status==='rejected');if(failed)throw failed.reason;
 const now=clock(),combined=combineSnapshots(previous.bundles,collected,now);report.publicationCheckedAt=now;report.errors.push(...combined.errors);
 const writeReport=()=>writeFile('coverage/refresh-report.json',JSON.stringify(report,null,2)+'\n');
 if(!process.env.DYNAMIC_COVERAGE_KEY_FILE){report.signing='missing_key';await writeReport();throw Error('Signing secret unavailable; previous signed manifest preserved');}
 if(!combined.bundles.length&&!combined.withdrawnOperators.length){report.signing='no_valid_bundles_previous_manifest_preserved';await writeReport();throw Error('No valid source snapshots; previous signed manifest preserved');}
 const catalog={schemaVersion:1,generatedAt:now,expiresAt:now+86400000,operators:cfg.operators};
 let previousManifest=null;try{previousManifest=JSON.parse(await readFile(out+'/v2/manifest.json'));}catch(error){if(error.code!=='ENOENT')throw error;}
 const legacy=legacyCompatibleBundles(combined.bundles,previous.legacyBundles,now);report.legacyConstraints=legacy.constraints;
 report.publication=await build({catalog,bundles:legacy.bundles,revision:previous.revision,keyFile:process.env.DYNAMIC_COVERAGE_KEY_FILE,out,now,allowEmptyPublication:legacy.constraints.length>0||combined.withdrawnOperators.length>0});
 report.cityPublication=await buildCityCoverage({catalog,bundles:combined.bundles,revision:previous.revision,keyFile:process.env.DYNAMIC_COVERAGE_KEY_FILE,out:out+'/v2',geography,now,previousManifest,sourceSnapshots:combined.sourceSnapshots,allowEmptyPublication:combined.withdrawnOperators.length>0});
 await writeReport();published=true;console.log(JSON.stringify({legacy:report.publication,cities:report.cityPublication}));return report;
 }finally{
  // The workflow can commit crawl cursors even when signing/publication fails.
  // Keep those cursors behind facts unless this invocation retained its facts
  // in both authenticated publications. Observation timestamps are untouched.
  if(!published)await Promise.all(cursorRollbacks.map(rollback=>rollback()));
 }
}
if(import.meta.url===pathToFileURL(process.argv[1]||'').href)await refresh();
