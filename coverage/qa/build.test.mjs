import {test} from 'node:test';import assert from 'node:assert/strict';import {validateBundle} from '../build.mjs';
const now=Date.now();const sample=()=>({schemaVersion:1,operatorId:'operator',generatedAt:now,expiresAt:now+60000,records:[{id:'house',official:true,regionId:'UA-46',settlement:'місто',community:'громада',street:'вулиця',scope:'house',houses:['1'],queue:'1.1',sourceUrl:'https://example.org/list',quote:'Official fields',checkedAt:now,expiresAt:now+60000}]});
test('accept bounded official house source',()=>assert.equal(validateBundle(sample(),now).records.length,1));
test('refuse expired and mixed subscriber queue records',()=>{const b=sample();b.records[0].expiresAt=now-1;assert.throws(()=>validateBundle(b,now));});
test('refuse street extrapolation',()=>{const b=sample();b.records[0].scope='street';assert.throws(()=>validateBundle(b,now));});
test('refuse duplicate records',()=>{const b=sample();b.records.push({...b.records[0]});assert.throws(()=>validateBundle(b,now));});
test('refuse non-HTTPS source',()=>{const b=sample();b.records[0].sourceUrl='http://example.org';assert.throws(()=>validateBundle(b,now));});
import {mergeSnapshots} from '../snapshots.mjs';
test('street refresh retains untouched old expiry, invalidates refreshed unknown house',()=>{
 const previous={records:[{id:'old',officialCityId:'1:2',expiresAt:now+5000},{id:'untouched',officialCityId:'1:3',expiresAt:now+10000},{id:'stale',officialCityId:'1:4',expiresAt:now-1}]};
 const fresh={completedStreetIds:['1:2'],records:[]};const result=mergeSnapshots(previous,fresh,now);assert.deepEqual(result.records,[previous.records[1]]);assert.equal(result.records[0].expiresAt,now+10000);
});
test('refuse accidental subscriber metadata in public record',()=>{const b=sample();b.records[0].accountId='private';assert.throws(()=>validateBundle(b,now));});
test('refuse records unsupported by client validator',()=>{for(const mutate of [r=>r.community='',r=>r.houses=['1'.repeat(31)],r=>r.houseRanges=['1-10'],r=>r.expiresAt=now+100000]){const b=sample();mutate(b.records[0]);assert.throws(()=>validateBundle(b,now));}});
test('post-collection clock accepts new observations without truncating their validity',()=>{
 const started=now,observed=started+1000,published=observed+5000;
 const fresh=sample();fresh.generatedAt=observed;fresh.expiresAt=observed+86400000;fresh.records[0].checkedAt=observed;fresh.records[0].expiresAt=fresh.expiresAt;
 const wrong=mergeSnapshots(null,fresh,started);assert.throws(()=>validateBundle(wrong,started));
 const merged=mergeSnapshots(null,fresh,published);assert.doesNotThrow(()=>validateBundle(merged,published));assert.equal(merged.records[0].expiresAt,fresh.records[0].expiresAt);assert.equal(merged.records[0].checkedAt,observed);
});
