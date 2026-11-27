// Offline import of explicitly reviewed public source bytes. This never fetches
// a source, signs data or renews an original source observation.
import {readFile,writeFile,mkdir,realpath,stat,readdir} from 'node:fs/promises';
import {resolve,relative,dirname,basename,sep} from 'node:path';
import {pathToFileURL} from 'node:url';
import {hash,validateBundle} from './build.mjs';
import {combineSnapshots} from './refresh.mjs';
import {validatePublisherSnapshot} from './publisher-snapshots.mjs';

const DAY=86400000,MAX_PACKET=16*1024*1024,MAX_SOURCE=4*1024*1024;
const same=(a,b)=>a===b;
function fields(value,allowed,label){
 if(!value||typeof value!=='object'||Array.isArray(value)||Object.keys(value).some(k=>!allowed.includes(k)))throw Error('invalid_'+label);
}
function https(value){try{const u=new URL(value);return u.protocol==='https:'&&!u.username&&!u.password&&!u.hash&&!u.port;}catch{return false;}}
function sourceHost(value){return new URL(value).hostname.replace(/^www\./,'');}
function shape(value,pattern,label){if(typeof value!=='string'||!pattern.test(value))throw Error('invalid_'+label);return value;}
async function containedFile(root,path,pattern,limit,sha,size){
 shape(path,pattern,'reviewed_file_path');
 const full=await realpath(resolve(root,path)),base=await realpath(root),rel=relative(base,full);
 if(!rel||rel==='..'||rel.startsWith('..'+sep)||resolve(base,rel)!==resolve(base,path))throw Error('reviewed_path_escape_or_symlink');
 const info=await stat(full);if(!info.isFile()||info.size>limit||size!==undefined&&info.size!==size)throw Error('reviewed_file_size');
 const raw=await readFile(full);if(hash(raw)!==sha)throw Error('reviewed_file_integrity');return raw;
}

export function validateReviewedSnapshot(review,packet,{operators,now=Date.now()}={}){
 fields(review,['schemaVersion','kind','operatorId','regionId','settlement','community','sourceUrl','observedAt','expiresAt','snapshot','source','reads','review'], 'review_descriptor');
 if(review.schemaVersion!==1||review.kind!=='reviewed-identical-public-document-snapshot')throw Error('unsupported_review_method');
 const operator=operators?.find(o=>o.id===review.operatorId);
 if(!operator||!/^UA-\d\d$/.test(review.regionId)||!operator.regionIds.includes(review.regionId)||!https(review.sourceUrl)||sourceHost(review.sourceUrl)!==sourceHost(operator.sourceUrl)||!['settlement','community'].every(k=>typeof review[k]==='string'&&review[k].length>0&&review[k].length<=500))throw Error('reviewed_operator_or_geography_mismatch');
 if(!Number.isSafeInteger(review.observedAt)||!Number.isSafeInteger(review.expiresAt)||review.observedAt>now||review.expiresAt<=now||review.expiresAt>review.observedAt+DAY)throw Error('reviewed_source_expired_or_future');
 fields(review.snapshot,['path','sha256','size'],'snapshot_descriptor');fields(review.source,['path','sha256','size'],'source_descriptor');
 for(const [key,max] of [['snapshot',MAX_PACKET],['source',MAX_SOURCE]]){
  const d=review[key];shape(d.sha256,/^[a-f0-9]{64}$/,'reviewed_digest');if(!Number.isSafeInteger(d.size)||d.size<1||d.size>max)throw Error('reviewed_file_size');
 }
 if(!Array.isArray(review.reads)||review.reads.length!==2)throw Error('two_original_source_reads_required');
 for(const r of review.reads){
  fields(r,['sourceUrl','finalUrl','status','checkedAt','sha256','bytes'],'source_read');
  if(r.sourceUrl!==review.sourceUrl||r.finalUrl!==review.sourceUrl||r.status!==200||r.sha256!==review.source.sha256||r.bytes!==review.source.size||!Number.isSafeInteger(r.checkedAt)||r.checkedAt>review.observedAt||r.checkedAt<review.observedAt-DAY)throw Error('reviewed_source_read_mismatch');
 }
 if(!(review.reads[0].checkedAt<review.reads[1].checkedAt&&review.reads[1].checkedAt===review.observedAt))throw Error('original_source_read_order_or_clock');
 if(typeof review.review!=='string'||!review.review.length||review.review.length>1000)throw Error('review_description_required');
 fields(packet,['schemaVersion','operatorId','generatedAt','expiresAt','records','observedHouses','completedStreetIds'],'reviewed_snapshot');
 if(packet.operatorId!==review.operatorId||packet.generatedAt!==review.observedAt||packet.expiresAt!==review.expiresAt||packet.completeSnapshot)throw Error('reviewed_snapshot_clock_or_operator_changed');
 validateBundle(packet,now);
 const geography=row=>['regionId','settlement','community'].every(k=>same(row[k],review[k]));
 const clock=row=>Number.isSafeInteger(row.checkedAt)&&row.checkedAt>=review.reads[0].checkedAt&&row.checkedAt<=review.observedAt&&Number.isSafeInteger(row.expiresAt)&&row.expiresAt>now&&row.expiresAt<=Math.min(review.expiresAt,row.checkedAt+DAY);
 for(const row of packet.records){if(!geography(row)||row.sourceUrl!==review.sourceUrl||!clock(row))throw Error('reviewed_record_scope_or_clock');}
 const observedKeys=['regionId','settlement','community','street','house','checkedAt','expiresAt','providerStreetId','officialCityId'];
 if(!Array.isArray(packet.observedHouses)||packet.observedHouses.length>100000)throw Error('reviewed_house_observations_required');
 for(const row of packet.observedHouses){
  fields(row,observedKeys,'house_observation');
  if(!geography(row)||!clock(row)||!['street','house'].every(k=>typeof row[k]==='string'&&row[k].length>0&&row[k].length<=(k==='house'?30:500))||['providerStreetId','officialCityId'].some(k=>row[k]!==undefined&&(typeof row[k]!=='string'||!row[k].length||row[k].length>150)))throw Error('reviewed_house_scope_or_clock');
 }
 if(packet.completedStreetIds?.length)throw Error('reviewed_import_cannot_withdraw_unobserved_streets');
 const merged=combineSnapshots([],[packet],now);
 if(merged.errors.length||merged.sourceSnapshots.length!==1)throw Error('reviewed_snapshot_merge_rejected');
 const normalized=merged.sourceSnapshots[0];validatePublisherSnapshot(normalized,now);
 return {snapshot:packet,normalized,summary:{operatorId:review.operatorId,sourceUrl:review.sourceUrl,originalObservedAt:review.observedAt,originalExpiresAt:review.expiresAt,records:packet.records.length,houseFacts:packet.records.reduce((n,r)=>n+(r.houses?.length||0),0),observedHouses:packet.observedHouses.length,negativeHouseWatermarks:normalized.negativeHouseWatermarks?.length||0,coverageMeasured:false}};
}

export async function stageReviewedSnapshot({root='.',reviewPath,reviewSha256,operatorId,staging,reportFile,now=Date.now()}={}){
 shape(reviewSha256,/^[a-f0-9]{64}$/,'review_digest');shape(operatorId,/^[-a-z0-9]+$/,'operator');
 if(basename(reviewPath||'')!==reviewSha256+'.json')throw Error('review_path_must_be_content_addressed');
 const raw=await containedFile(root,reviewPath,/^coverage\/reviewed\/reviews\/[a-f0-9]{64}\.json$/,64*1024,reviewSha256);
 const review=JSON.parse(raw);if(review.operatorId!==operatorId)throw Error('requested_review_operator_mismatch');
 const operators=JSON.parse(await readFile(resolve(root,'coverage/sources.json'))).operators;
 const packetRaw=await containedFile(root,review.snapshot?.path,/^coverage\/reviewed\/snapshots\/[a-f0-9]{64}\.json$/,MAX_PACKET,review.snapshot?.sha256,review.snapshot?.size);
 if(basename(review.snapshot.path)!==review.snapshot.sha256+'.json')throw Error('snapshot_path_must_be_content_addressed');
 const sourceRaw=await containedFile(root,review.source?.path,/^coverage\/reviewed\/sources\/[a-f0-9]{64}\.html$/,MAX_SOURCE,review.source?.sha256,review.source?.size);
 if(basename(review.source.path)!==review.source.sha256+'.html')throw Error('source_path_must_be_content_addressed');
 const value=validateReviewedSnapshot(review,JSON.parse(packetRaw),{operators,now});
 // Keep the exact reviewed source and input packet bytes; no reparsing or
 // timestamp substitution is hidden in this import step.
 await mkdir(staging,{recursive:true});if((await readdir(staging)).length)throw Error('reviewed_staging_must_be_empty');
 const target=resolve(staging,operatorId+'.json');await writeFile(target,packetRaw,{flag:'wx'});
 const report={schemaVersion:1,method:'offline-SHA-bound-reviewed-public-source-import',reviewPath,reviewSha256,snapshotSha256:hash(packetRaw),sourceSha256:hash(sourceRaw),...value.summary,networkRequests:0,sourceClocksRenewed:false,signed:false,publishedToApkChannel:false};
 await mkdir(dirname(reportFile),{recursive:true});await writeFile(reportFile,JSON.stringify(report,null,2)+'\n');return report;
}

if(import.meta.url===pathToFileURL(process.argv[1]||'').href){
 const [reviewPath,reviewSha256,operatorId,staging,reportFile]=process.argv.slice(2);
 if(!reportFile||process.argv.length!==7)throw Error('Usage: node coverage/import-reviewed-snapshot.mjs review-path review-sha256 operator staging report-file');
 console.log(JSON.stringify(await stageReviewedSnapshot({reviewPath,reviewSha256,operatorId,staging,reportFile})));
}
