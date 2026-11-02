import test from 'node:test';import assert from 'node:assert/strict';
import {combineSnapshots,liveSnapshot,prepareDtekSnapshot} from '../refresh.mjs';import {compactSnapshot,mergeSnapshots} from '../snapshots.mjs';
const at=10000,expiresAt=at+3600000;
const row=(id,house,queue='1.1',extra={})=>({id,official:true,regionId:'UA-46',settlement:'Зразок',community:'Зразкова',street:'Нова',scope:'house',houses:[house],queue,sourceUrl:'https://example.org/source',quote:'Зразок, Нова, будинок '+house+', черга '+queue,quoteType:'structured-official-fields',checkedAt:at,expiresAt,...extra});
const packet=records=>({schemaVersion:1,operatorId:'lviv',generatedAt:at,expiresAt,records});
test('one expired row cannot discard other still-live source assignments',()=>{
 const b=packet([row('old','1','1.1',{expiresAt:at+1000}),row('fresh','2')]);assert.deepEqual(liveSnapshot(b,at+1001).records.map(r=>r.id),['fresh']);
});
test('house grouping preserves each original deadline and remains a literal house list',()=>{
 const b=compactSnapshot(packet([row('a','1'),row('b','2'),row('c','3','1.1',{checkedAt:at-1})]));assert.equal(b.records.length,2);assert.deepEqual(b.records.find(r=>r.checkedAt===at).houses,['1','2']);assert(b.records.every(r=>r.scope==='house'&&r.expiresAt===expiresAt));
});
test('a partial fresh house replaces its prior group member without dropping untouched houses',()=>{
 const old=compactSnapshot(packet([row('a','1'),row('b','2')]));const b=mergeSnapshots(old,{...packet([row('new','1','2.1',{checkedAt:at+1})]),generatedAt:at+1},at+1);assert.equal(b.records.filter(r=>r.houses.includes('1')).length,1);assert.equal(b.records.find(r=>r.houses.includes('1')).queue,'2.1');assert(b.records.some(r=>r.houses.includes('2')));
});
test('different official street identities are preserved for user selection',()=>{
 const a=row('a','1','1.1',{officialCityId:'branch-a'}),b=row('b','1','1.1',{officialCityId:'branch-b'});const merged=mergeSnapshots(packet([a]),packet([b]),at);assert.equal(compactSnapshot(merged).records.length,2);
});
test('a failed or incompatible fresh source does not replace previous live data',()=>{
 const old=packet([row('old','1')]),fresh=packet([row('bad','2','0',{account:'private'})]);const r=combineSnapshots([old],[fresh],at);assert.equal(r.bundles[0].records[0].id,'old');assert.equal(r.errors.length,1);
});
test('new DTEK streets do not inherit the old street city selector or discard old houses',()=>{
 const previous={...packet([row('old','1','1.1',{officialCityId:'Зразок'})]),operatorId:'dtek-odesa'};
 const fresh={...packet([row('observed','1','1.1'),row('new','2','2.1',{street:'Інша'})]),operatorId:'dtek-odesa'};
 const result=combineSnapshots([previous],[fresh],at);assert.equal(result.errors.length,0);
 assert.equal(result.bundles[0].records.find(r=>r.street==='Нова').officialCityId,'Зразок');
 assert.equal(result.bundles[0].records.find(r=>r.street==='Інша').officialCityId,undefined);
 assert.deepEqual(result.bundles[0].records.flatMap(r=>r.houses).sort(),['1','2']);
});
test('old collector city-only fields are removed on new streets while branch identities remain',()=>{
 const fresh={...packet([row('a','1','1.1',{officialCityId:'Зразок'}),row('b','2','2.1',{street:'Інша',officialCityId:'branch:street'})]),operatorId:'dtek-odesa'};
 const normalized=prepareDtekSnapshot(null,fresh);assert.equal(normalized.records[0].officialCityId,undefined);assert.equal(normalized.records[1].officialCityId,'branch:street');assert.equal(normalized.records[0].checkedAt,at);assert.equal(normalized.records[0].expiresAt,expiresAt);
 assert.equal(prepareDtekSnapshot(null,{...fresh,operatorId:'lviv'}).records[0].officialCityId,'Зразок');
});
test('malformed DTEK collection cannot abort publication or replace working data',()=>{
 const old={...packet([row('old','1')]),operatorId:'dtek-odesa'};
 const result=combineSnapshots([old],[{operatorId:'dtek-odesa',records:[null]}],at);
 assert.equal(result.errors.length,1);assert.equal(result.bundles[0].records[0].id,'old');
});
test('spacing after a street abbreviation cannot duplicate a retained legacy selector',()=>{
 const old={...packet([row('old','1','1.1',{street:'вул. Нова',officialCityId:'Зразок'})]),operatorId:'dtek-odesa'};
 const fresh={...packet([row('fresh','1','1.1',{street:'вул.Нова'})]),operatorId:'dtek-odesa'};
 const result=combineSnapshots([old],[fresh],at);assert.equal(result.errors.length,0);assert.equal(result.bundles[0].records.length,1);assert.equal(result.bundles[0].records[0].officialCityId,'Зразок');assert.equal(result.bundles[0].records[0].street,'вул. Нова');
});

test('source-type suffix spacing cannot invalidate an otherwise working complete city refresh',()=>{
 const previous={...packet([row('old','1','1.1',{street:'ЗРАЗКОВА.ПРОВ.1',officialCityId:'branch:street'})]),operatorId:'chernivtsi'};
 const fresh={...packet([row('new','1','1.1',{street:'ЗРАЗКОВА.ПРОВ. 1',officialCityId:'branch:street'})]),operatorId:'chernivtsi'};
 const result=combineSnapshots([previous],[fresh],at);assert.equal(result.errors.length,0);assert.equal(result.bundles[0].records.length,1);
});
