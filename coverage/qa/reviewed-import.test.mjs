import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,mkdir,readFile,writeFile,stat,symlink} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {resolve} from 'node:path';
import {hash} from '../build.mjs';
import {stageReviewedSnapshot,validateReviewedSnapshot} from '../import-reviewed-snapshot.mjs';

const at=1000000,now=at+1000,expiresAt=at+86400000;
const operators=[{id:'training',sourceUrl:'https://example.org/roster',regionIds:['UA-73']}];
function fixture(){
 const row={id:'observed-house',official:true,regionId:'UA-73',settlement:'Навчальне',community:'Навчальна громада',street:'вул. Прикладна',scope:'house',houses:['1а'],queue:'1.1',sourceUrl:'https://example.org/roster',quote:'Навчальне, вул. Прикладна, будинок1а: черга1.1',quoteType:'structured-official-fields',checkedAt:at,expiresAt};
 const observation={regionId:row.regionId,settlement:row.settlement,community:row.community,street:row.street,house:'1а',checkedAt:at,expiresAt};
 const packet={schemaVersion:1,operatorId:'training',generatedAt:at,expiresAt,records:[row],observedHouses:[observation,{...observation,house:'2'}]};
 const packetRaw=Buffer.from(JSON.stringify(packet)+'\n'),sourceRaw=Buffer.from('<html>Public literal house roster, first and confirmation read.</html>');
 const review={schemaVersion:1,kind:'reviewed-identical-public-document-snapshot',operatorId:'training',regionId:row.regionId,settlement:row.settlement,community:row.community,sourceUrl:row.sourceUrl,observedAt:at,expiresAt,snapshot:{path:'coverage/reviewed/snapshots/'+hash(packetRaw)+'.json',sha256:hash(packetRaw),size:packetRaw.length},source:{path:'coverage/reviewed/sources/'+hash(sourceRaw)+'.html',sha256:hash(sourceRaw),size:sourceRaw.length},reads:[at-1000,at].map(checkedAt=>({sourceUrl:row.sourceUrl,finalUrl:row.sourceUrl,status:200,checkedAt,sha256:hash(sourceRaw),bytes:sourceRaw.length})),review:'Independent literal source review; no Android automatic coverage claim.'};
 return {packet,packetRaw,sourceRaw,review};
}
async function workspace(){
 const root=await mkdtemp(tmpdir()+'/reviewed-source-'),f=fixture();
 const raw=Buffer.from(JSON.stringify(f.review)+'\n'),reviewSha256=hash(raw),reviewPath='coverage/reviewed/reviews/'+reviewSha256+'.json';
 for(const [path,value] of [[reviewPath,raw],[f.review.snapshot.path,f.packetRaw],[f.review.source.path,f.sourceRaw],['coverage/sources.json',JSON.stringify({operators})]]){
  await mkdir(resolve(root,path,'..'),{recursive:true});await writeFile(resolve(root,path),value);
 }
 return {root,...f,reviewPath,reviewSha256,operatorId:'training',staging:root+'/temporary-staging',reportFile:root+'/receipt/import.json',now};
}
test('exact SHA-bound original bytes stage without network, signing, source clock renewal or APK channel writes',async()=>{
 const w=await workspace(),before=structuredClone(w.packet),oldFetch=globalThis.fetch;
 globalThis.fetch=()=>{throw Error('A reviewed import must never fetch a source');};
 try{
  const r=await stageReviewedSnapshot(w);
  assert.deepEqual(await readFile(w.staging+'/training.json'),w.packetRaw);
  assert.equal(r.originalObservedAt,at);assert.equal(r.originalExpiresAt,expiresAt);assert.equal(r.houseFacts,1);assert.equal(r.negativeHouseWatermarks,1);
  assert.equal(r.networkRequests,0);assert.equal(r.sourceClocksRenewed,false);assert.equal(r.signed,false);assert.equal(r.publishedToApkChannel,false);
  assert.deepEqual(JSON.parse(await readFile(w.staging+'/training.json')),before);
  await assert.rejects(()=>stat(w.root+'/latest.json'),{code:'ENOENT'});
  await assert.rejects(()=>stat(w.root+'/dynamic-coverage/manifest.json'),{code:'ENOENT'});
 }finally{globalThis.fetch=oldFetch;}
});
test('expired or future observation, altered packet clocks and renewed per-house clocks fail before staging',async()=>{
 const f=fixture();
 for(const [r,p] of [
  [{...f.review,expiresAt:now},f.packet],
  [{...f.review,observedAt:now+1},f.packet],
  [f.review,{...f.packet,generatedAt:now}],
  [f.review,{...f.packet,records:[{...f.packet.records[0],checkedAt:now}]}],
  [f.review,{...f.packet,observedHouses:[{...f.packet.observedHouses[0],expiresAt:expiresAt+1}]}]
 ])assert.throws(()=>validateReviewedSnapshot(r,p,{operators,now}));
});
test('both distinct original successful reads must bind the same exact source bytes, URL and last observed clock',()=>{
 const f=fixture();
 for(const change of [{status:403},{finalUrl:'https://another.example/roster'},{sha256:'0'.repeat(64)},{checkedAt:at+1},{bytes:f.sourceRaw.length+1}]){
  const review=structuredClone(f.review);Object.assign(review.reads[0],change);assert.throws(()=>validateReviewedSnapshot(review,f.packet,{operators,now}));
 }
 for(const reads of [[],[f.review.reads[0]],[f.review.reads[1],f.review.reads[1]],[f.review.reads[1],f.review.reads[0]]])assert.throws(()=>validateReviewedSnapshot({...f.review,reads},f.packet,{operators,now}));
});
test('same geographic and source scope is required for every positive and negative house observation',()=>{
 const f=fixture();
 for(const key of ['regionId','settlement','community','sourceUrl']){
  const p=structuredClone(f.packet);p.records[0][key]=key==='sourceUrl'?'https://unrelated.example/':'other';assert.throws(()=>validateReviewedSnapshot(f.review,p,{operators,now}));
 }
 for(const change of [{community:'Інша громада'},{checkedAt:at-2000},{accountId:'must-not-publish'},{house:''}]){
  const p=structuredClone(f.packet);Object.assign(p.observedHouses[0],change);assert.throws(()=>validateReviewedSnapshot(f.review,p,{operators,now}));
 }
 assert.throws(()=>validateReviewedSnapshot({...f.review,sourceUrl:'https://unrelated.example/'},f.packet,{operators,now}));
 assert.throws(()=>validateReviewedSnapshot(f.review,{...f.packet,completeSnapshot:true},{operators,now}));
 assert.throws(()=>validateReviewedSnapshot(f.review,{...f.packet,completedStreetIds:['unobserved']},{operators,now}));
 assert.throws(()=>validateReviewedSnapshot(f.review,{...f.packet,negativeHouseWatermarks:[]},{operators,now}));
});
test('tampered descriptor, packet or raw primary source bytes cannot enter the signing staging directory',async()=>{
 for(const part of ['review','snapshot','source']){
  const w=await workspace();const path=part==='review'?w.reviewPath:w.review[part].path;
  await writeFile(resolve(w.root,path),Buffer.from('tampered'));
  await assert.rejects(()=>stageReviewedSnapshot(w),/integrity|size/);
  await assert.rejects(()=>stat(w.staging),{code:'ENOENT'});
 }
});
test('wrong operator, non-content-addressed input, traversal and shell-shaped input are rejected before staging',async()=>{
 const w=await workspace();
 for(const change of [{operatorId:'other'},{reviewSha256:'0'.repeat(64)},{reviewPath:'../private.json'},{reviewPath:'/tmp/review.json'},{reviewPath:'coverage/reviewed/reviews/$(cat secret).json'}]){
  await assert.rejects(()=>stageReviewedSnapshot({...w,...change}));
  await assert.rejects(()=>stat(w.staging),{code:'ENOENT'});
 }
});
test('a reviewed repository path cannot read a symlink outside its pinned location or overwrite previous staging',async()=>{
 const w=await workspace();
 await mkdir(w.staging);await writeFile(w.staging+'/previous.json','retained');
 await assert.rejects(()=>stageReviewedSnapshot(w),/must_be_empty/);assert.equal(await readFile(w.staging+'/previous.json','utf8'),'retained');
 const other=await workspace();const sourcePath=resolve(other.root,other.review.source.path);
 const {unlink}=await import('node:fs/promises');await unlink(sourcePath);await symlink(sourcePath+'.outside',sourcePath);await writeFile(sourcePath+'.outside',other.sourceRaw);
 await assert.rejects(()=>stageReviewedSnapshot(other),/escape_or_symlink/);
 await assert.rejects(()=>stat(other.staging),{code:'ENOENT'});
});
