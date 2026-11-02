import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,mkdir,writeFile,readFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {generateKeyPairSync,sign} from 'node:crypto';
import {hash,BASE} from '../build.mjs';
import {storeSourceSnapshots,readSourceSnapshots,MAX_SOURCE_SNAPSHOT} from '../publisher-snapshots.mjs';
import {legacyCompatibleBundles} from '../legacy-compat.mjs';
import {previousSnapshot,combineSnapshots} from '../refresh.mjs';
import {cityShards} from '../build-v2.mjs';
import {mergeSnapshots} from '../snapshots.mjs';
const now=100000,expiresAt=now+3600000;
const row=(id,extra={})=>({id:String(id),official:true,regionId:'UA-46',settlement:'Навчальне',community:'Навчальна громада',street:'вул. Нова',scope:'house',houses:[String(Number(id)+1)],queue:'1.1',sourceUrl:'https://example.org/official',quote:'Official house fields '+String(id),checkedAt:now,expiresAt,...extra});
const packet=records=>({schemaVersion:1,operatorId:'lviv',generatedAt:now,expiresAt,records});
const {privateKey,publicKey}=generateKeyPairSync('ed25519');
function envelope(value){const payload=Buffer.from(JSON.stringify(value));return {schemaVersion:value.schemaVersion,keyId:'coverage-v1',payload:payload.toString('base64'),signature:sign(null,payload,privateKey).toString('base64')};}
function manifest(schemaVersion,extra={}){return {schemaVersion,minClientVersion:schemaVersion,revision:7,generatedAt:now,expiresAt,enabled:true,bundles:[],...extra};}
async function writeSigned(out,name,value){await writeFile(out+'/'+name,JSON.stringify(envelope(value)));}

test('oversize legacy operator retains only its authenticated live subset, full two-city source survives failed next collection',async()=>{
 const out=await mkdtemp(tmpdir()+'/publisher-retention-');await mkdir(out+'/bundles');await mkdir(out+'/v2');
 const rows=Array.from({length:4000},(_,i)=>row(i,{settlement:i<2000?'Навчальне':'Друге',quote:'Official literal observation '+i+' '+'.'.repeat(1950)})),full=packet(rows),old=packet([rows[0]]);
 assert(Buffer.byteLength(JSON.stringify(full))>8*1024*1024);
 const legacy=legacyCompatibleBundles([full],[old],now+1);assert.equal(legacy.constraints.length,1);assert.equal(legacy.bundles[0].records.length,1);
 assert.equal(legacy.bundles[0].generatedAt,now);assert.equal(legacy.bundles[0].records[0].expiresAt,expiresAt);
 const bytes=Buffer.from(JSON.stringify(old)+'\n'),sha256=hash(bytes);await writeFile(out+'/bundles/'+sha256+'.json',bytes);
 await writeSigned(out,'manifest.json',manifest(1,{bundles:[{operatorId:'lviv',url:BASE+'bundles/'+sha256+'.json',sha256,size:bytes.length,expiresAt}]}));
 const source=await storeSourceSnapshots([full],out+'/v2',now+1);await writeSigned(out,'v2/manifest.json',manifest(2,{sourceSnapshots:source.descriptors}));
 const restored=await previousSnapshot(out,now+2,{publicKey});assert.equal(restored.revision,8);assert.equal(restored.legacyBundles[0].records.length,1);assert.equal(restored.bundles[0].records.length,4000);
 const failedNext=combineSnapshots(restored.bundles,[],now+3);assert.equal(failedNext.bundles[0].records.length,4000);assert.equal(cityShards(failedNext.bundles,{now:now+3}).length,2);assert.deepEqual(failedNext.withdrawnOperators,[]);
 assert(failedNext.bundles[0].records.every(r=>r.checkedAt===now&&r.expiresAt===expiresAt));
});

test('source cache rejects path/size/hash corruption and accidental subscriber fields before they can shrink a city index',async()=>{
 const out=await mkdtemp(tmpdir()+'/publisher-integrity-'),b=packet([row(1)]),cache=await storeSourceSnapshots([b],out,now);
 const m=manifest(2,{sourceSnapshots:cache.descriptors});
 for(const patch of [{url:'https://evil.example/data'},{sha256:'../escape'},{size:MAX_SOURCE_SNAPSHOT+1},{size:1},{expiresAt:expiresAt+1}]){
  const bad=structuredClone(m);Object.assign(bad.sourceSnapshots[0],patch);await assert.rejects(()=>readSourceSnapshots(bad,out,now+1));
 }
 const path=out+'/sources/'+cache.descriptors[0].sha256+'.json';await writeFile(path,'corrupt');await assert.rejects(()=>readSourceSnapshots(m,out,now+1),/integrity/);
 await assert.rejects(()=>storeSourceSnapshots([packet([row(1,{accountId:'must-never-be-public'})])],out,now),/unexpected_record_field/);
});

test('restore checks the signed parent before following source snapshots and retains revision across expiry',async()=>{
 const out=await mkdtemp(tmpdir()+'/publisher-signature-');await mkdir(out+'/v2');
 const value=manifest(2,{sourceSnapshots:[]}),signed=envelope(value);signed.signature=signed.signature.replace(/^./,signed.signature[0]==='A'?'B':'A');await writeFile(out+'/v2/manifest.json',JSON.stringify(signed));
 await assert.rejects(()=>previousSnapshot(out,now+1,{publicKey}),/unverified_previous/);
 await writeSigned(out,'v2/manifest.json',value);const expired=await previousSnapshot(out,expiresAt+1,{publicKey});assert.equal(expired.revision,8);assert.deepEqual(expired.bundles,[]);
 const cache=await storeSourceSnapshots([packet([row(1)])],out+'/v2',now);await writeSigned(out,'v2/manifest.json',manifest(2,{enabled:false,sourceSnapshots:cache.descriptors}));
 const disabled=await previousSnapshot(out,now+1,{publicKey});assert.deepEqual(disabled.bundles,[]);
});

test('newly unknown house removes Latin/hyphen aliases but not a fraction or another provider street',()=>{
 const old=packet([row(1,{houses:['1-А','1/2','12'],providerStreetId:'street-1'}),row(2,{houses:['1А'],providerStreetId:'street-2'})]);
 const fresh={...packet([]),observedHouses:[{regionId:'UA-46',settlement:'Навчальне',community:'Навчальна громада',street:'вул. Нова',house:'1A',providerStreetId:'street-1'}]};
 const result=mergeSnapshots(old,fresh,now+1);assert.deepEqual(result.records[0].houses,['1/2','12']);assert.deepEqual(result.records[1].houses,['1А']);
});

test('a successful negative source observation withdraws the last old operator instead of preserving its queue',()=>{
 const old=packet([row(1,{houses:['1-А']})]),fresh={...packet([]),observedHouses:[{regionId:'UA-46',settlement:'Навчальне',community:'Навчальна громада',street:'вул. Нова',house:'1A'}]};
 const result=combineSnapshots([old],[fresh],now+1);assert.deepEqual(result.bundles,[]);assert.deepEqual(result.withdrawnOperators,['lviv']);assert.deepEqual(result.errors,[]);
});
