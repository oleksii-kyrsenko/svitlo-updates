import test from 'node:test';import assert from 'node:assert/strict';
import {mkdtemp,mkdir,writeFile} from 'node:fs/promises';import {tmpdir} from 'node:os';import {generateKeyPairSync,sign} from 'node:crypto';
import {mergeSnapshots} from '../snapshots.mjs';import {combineSnapshots,previousSnapshot} from '../refresh.mjs';import {storeSourceSnapshots} from '../publisher-snapshots.mjs';import {hash,BASE} from '../build.mjs';
const at=100000,geo={regionId:'UA-46',settlement:'Навчальне',community:'Навчальна громада',street:'вул. Нова',providerStreetId:'s1'};
const row=(checkedAt,queue='1.1',extra={})=>({id:'same-source-id',official:true,...geo,scope:'house',houses:['1-А'],queue,sourceUrl:'https://example.org/official',quote:'Literal official queue observation',checkedAt,expiresAt:checkedAt+20000,...extra});
const packet=(records,generatedAt=at,extra={})=>({schemaVersion:1,operatorId:'lviv',generatedAt,expiresAt:generatedAt+20000,records,...extra});
const observation=(checkedAt,extra={})=>({...geo,house:'1A',checkedAt,expiresAt:checkedAt+20000,...extra});

test('older house staging never rolls a newer queue back, even if source row ID is reused',()=>{
 const current=packet([row(at+500,'2.1')],at+500),staging=packet([row(at+100,'1.1')],at+100);
 const merged=mergeSnapshots(current,staging,at+1000);assert.equal(merged.records.length,1);assert.equal(merged.records[0].queue,'2.1');assert.equal(merged.records[0].checkedAt,at+500);assert.equal(merged.records[0].expiresAt,at+20500);
});

test('older unknown and completed/full snapshot cannot erase a more recent house observation',()=>{
 const current=packet([row(at+500,'2.1',{officialCityId:'city:street'})],at+500),staging=packet([row(at+100,'1.1',{id:'other',houses:['2'],officialCityId:'city:street'})],at+100,{observedHouses:[observation(at+200)],completedStreetIds:['city:street'],completeSnapshot:true});
 const merged=combineSnapshots([current],[staging],at+1000);assert.equal(merged.errors.length,0);assert(merged.bundles[0].records.some(r=>r.houses.includes('1-А')&&r.queue==='2.1'));assert.equal(merged.sourceSnapshots[0].negativeHouseWatermarks.length,0);
});

test('a newer unknown removes the old queue and preserves the original negative deadline through a staging replay',()=>{
 const current=packet([row(at+100,'1.1')],at+100),unknown=packet([],at+700,{observedHouses:[observation(at+600,{expiresAt:at+1600})]});
 const removed=combineSnapshots([current],[unknown],at+800);assert.deepEqual(removed.bundles,[]);assert.deepEqual(removed.withdrawnOperators,['lviv']);
 const state=removed.sourceSnapshots[0];assert.equal(state.negativeHouseWatermarks[0].checkedAt,at+600);assert.equal(state.negativeHouseWatermarks[0].expiresAt,at+1600);
 const replay=combineSnapshots(removed.sourceSnapshots,[packet([row(at+200,'1.1')],at+200)],at+900);assert.deepEqual(replay.bundles,[]);assert.equal(replay.sourceSnapshots[0].negativeHouseWatermarks[0].expiresAt,at+1600);
 const restored=combineSnapshots(replay.sourceSnapshots,[packet([row(at+1000,'3.1')],at+1000)],at+1100);assert.equal(restored.bundles[0].records[0].queue,'3.1');assert.equal(restored.sourceSnapshots[0].negativeHouseWatermarks.length,0);assert.equal(restored.bundles[0].records[0].checkedAt,at+1000);
});

test('all-negative operator survives signed cache write/read and blocks an old positive after process restart',async()=>{
 const current=packet([row(at+100)],at+100),unknown=packet([],at+700,{observedHouses:[observation(at+600,{expiresAt:at+1600})]}),removed=combineSnapshots([current],[unknown],at+800);
 const out=await mkdtemp(tmpdir()+'/negative-house-restart-');await mkdir(out+'/v2');await mkdir(out+'/bundles');const cache=await storeSourceSnapshots(removed.sourceSnapshots,out+'/v2',at+800);assert.equal(cache.descriptors.length,1);
 const {privateKey,publicKey}=generateKeyPairSync('ed25519'),payload=Buffer.from(JSON.stringify({schemaVersion:2,minClientVersion:2,enabled:true,revision:9,generatedAt:at+800,expiresAt:at+1600,bundles:[],retiredCities:[],sourceSnapshots:cache.descriptors}));
 await writeFile(out+'/v2/manifest.json',JSON.stringify({schemaVersion:2,keyId:'coverage-v1',payload:payload.toString('base64'),signature:sign(null,payload,privateKey).toString('base64')}));
 const oldBytes=Buffer.from(JSON.stringify(current)),sha256=hash(oldBytes);await writeFile(out+'/bundles/'+sha256+'.json',oldBytes);const oldPayload=Buffer.from(JSON.stringify({schemaVersion:1,minClientVersion:1,enabled:true,revision:8,generatedAt:at+100,expiresAt:current.expiresAt,bundles:[{operatorId:'lviv',url:BASE+'bundles/'+sha256+'.json',sha256,size:oldBytes.length,expiresAt:current.expiresAt}]}));await writeFile(out+'/manifest.json',JSON.stringify({schemaVersion:1,keyId:'coverage-v1',payload:oldPayload.toString('base64'),signature:sign(null,oldPayload,privateKey).toString('base64')}));
 const previous=await previousSnapshot(out,at+900,{publicKey});assert.equal(previous.legacyBundles[0].records.length,1);assert.equal(previous.bundles[0].records.length,0);assert.equal(previous.bundles[0].negativeHouseWatermarks[0].expiresAt,at+1600);
 const replay=combineSnapshots(previous.bundles,[packet([row(at+200)],at+200)],at+1000);assert.deepEqual(replay.bundles,[]);assert.equal(replay.sourceSnapshots[0].negativeHouseWatermarks[0].checkedAt,at+600);
});

test('partial group update with the same row ID retains untouched members instead of overwriting the group',()=>{
 const old=packet([row(at+100,'1.1',{houses:['1-А','2']})],at+100),fresh=packet([row(at+200,'2.1')],at+200),merged=mergeSnapshots(old,fresh,at+300);
 assert.equal(merged.records.length,2);assert.equal(new Set(merged.records.map(r=>r.id)).size,2);assert(merged.records.some(r=>r.houses.length===1&&r.houses[0]==='2'&&r.queue==='1.1'));assert(merged.records.some(r=>r.houses.includes('1-А')&&r.queue==='2.1'));
});

test('contradictory equal-time positive assignments remain ambiguous and a tie cannot supersede a negative watermark',()=>{
 const old=packet([row(at+100,'1.1')],at+100),fresh=packet([row(at+100,'2.1')],at+100),merged=mergeSnapshots(old,fresh,at+200);assert.deepEqual(new Set(merged.records.map(r=>r.queue)),new Set(['1.1','2.1']));
 const negative=combineSnapshots([old],[packet([],at+300,{observedHouses:[observation(at+250)]})],at+400);
 const tied=combineSnapshots(negative.sourceSnapshots,[packet([row(at+250,'3.1')],at+250)],at+500);assert.deepEqual(tied.bundles,[]);
});
