import test from 'node:test';import assert from 'node:assert/strict';
import {combineSnapshots,liveSnapshot} from '../refresh.mjs';import {compactSnapshot,mergeSnapshots} from '../snapshots.mjs';
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
 const old=compactSnapshot(packet([row('a','1'),row('b','2')]));const b=mergeSnapshots(old,packet([row('new','1','2.1')]),at);assert.equal(b.records.filter(r=>r.houses.includes('1')).length,1);assert.equal(b.records.find(r=>r.houses.includes('1')).queue,'2.1');assert(b.records.some(r=>r.houses.includes('2')));
});
test('different official street identities are preserved for user selection',()=>{
 const a=row('a','1','1.1',{officialCityId:'branch-a'}),b=row('b','1','1.1',{officialCityId:'branch-b'});const merged=mergeSnapshots(packet([a]),packet([b]),at);assert.equal(compactSnapshot(merged).records.length,2);
});
test('a failed or incompatible fresh source does not replace previous live data',()=>{
 const old=packet([row('old','1')]),fresh=packet([row('bad','2','0',{account:'private'})]);const r=combineSnapshots([old],[fresh],at);assert.equal(r.bundles[0].records[0].id,'old');assert.equal(r.errors.length,1);
});
