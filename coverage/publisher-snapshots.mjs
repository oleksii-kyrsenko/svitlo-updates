// Publisher-only full source cache. Descriptors are authenticated by the v2
// envelope. Phones ignore them and fetch only their selected city package.
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {hash,validateBundle} from './build.mjs';
export const SOURCE_PREFIX='https://raw.githubusercontent.com/oleksii-kyrsenko/svitlo-updates/main/dynamic-coverage/v2/sources/';
export const MAX_SOURCE_SNAPSHOT=64*1024*1024;
export async function storeSourceSnapshots(bundles,out,now=Date.now()){
 await mkdir(out+'/sources',{recursive:true});const descriptors=[],skipped=[];
 for(const b of bundles){
  validateBundle(b,now);
  // Store only normalized public facts; operational error/context fields are
  // not carried into a source snapshot or into the app's runtime packets.
  const source={schemaVersion:1,operatorId:b.operatorId,generatedAt:b.generatedAt,expiresAt:b.expiresAt,records:b.records};
  const bytes=Buffer.from(JSON.stringify(source)+'\n');
  if(bytes.length>MAX_SOURCE_SNAPSHOT)throw Object.assign(Error('oversize_publisher_source_snapshot'),{operatorId:b.operatorId,bytes:bytes.length});
  const sha256=hash(bytes);await writeFile(out+'/sources/'+sha256+'.json',bytes);
  descriptors.push({operatorId:b.operatorId,url:SOURCE_PREFIX+sha256+'.json',sha256,size:bytes.length,expiresAt:b.expiresAt});
 }
 return {descriptors,skipped};
}
// Caller MUST verify the parent v2 signature before supplying this manifest.
// Any corrupt referenced cache aborts publication rather than shrinking the
// current city index and pretending a collector withdrew the missing data.
export async function readSourceSnapshots(manifest,out,now=Date.now()){
 if(manifest.sourceSnapshots===undefined)return [];
 if(!Array.isArray(manifest.sourceSnapshots)||manifest.sourceSnapshots.length>100)throw Error('invalid_source_snapshot_index');
 const ids=new Set(),bundles=[];
 for(const e of manifest.sourceSnapshots){
  if(!/^[-a-z0-9]+$/.test(e.operatorId)||ids.has(e.operatorId)||!/^[a-f0-9]{64}$/.test(e.sha256)||e.url!==SOURCE_PREFIX+e.sha256+'.json'||!Number.isSafeInteger(e.size)||e.size<1||e.size>MAX_SOURCE_SNAPSHOT||!Number.isFinite(e.expiresAt)||e.expiresAt>manifest.expiresAt)throw Error('invalid_source_snapshot_descriptor');
  ids.add(e.operatorId);if(e.expiresAt<=now)continue;
  const raw=await readFile(out+'/sources/'+e.sha256+'.json');if(raw.length!==e.size||hash(raw)!==e.sha256)throw Error('source_snapshot_integrity');
  const b=JSON.parse(raw);validateBundle(b,b.generatedAt);
  if(b.operatorId!==e.operatorId||b.expiresAt!==e.expiresAt||b.generatedAt>now||b.expiresAt<=now)throw Error('source_snapshot_metadata');
  const live={...b,records:b.records.filter(r=>r.expiresAt>now)};if(live.records.length){validateBundle(live,now);bundles.push(live);}
 }
 return bundles;
}
