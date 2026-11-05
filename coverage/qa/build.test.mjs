import {test} from 'node:test';import assert from 'node:assert/strict';import {validateBundle,validatePublishedBundle} from '../build.mjs';
const now=Date.now();const sample=()=>({schemaVersion:1,operatorId:'operator',generatedAt:now,expiresAt:now+60000,records:[{id:'house',official:true,regionId:'UA-46',settlement:'місто',community:'громада',street:'вулиця',scope:'house',houses:['1'],queue:'1.1',sourceUrl:'https://example.org/list',quote:'Official fields',checkedAt:now,expiresAt:now+60000}]});
test('accept bounded official house source',()=>assert.equal(validateBundle(sample(),now).records.length,1));
test('a row expiring after publication does not invalidate other live rows or renew any source clock',()=>{
 const b=sample();b.records[0].expiresAt=now+1000;b.records.push({...b.records[0],id:'later',houses:['2'],expiresAt:now+60000});
 const original=structuredClone(b);assert.doesNotThrow(()=>validatePublishedBundle(b,now+2000));assert.deepEqual(b,original);
 assert.throws(()=>validateBundle(b,now+2000),/invalid_record/,'a fresh source input still cannot contain an expired row');
});
test('published verification rejects rows already invalid at snapshot creation',()=>{
 for(const mutate of [r=>r.expiresAt=now,r=>r.checkedAt=now+1,r=>r.sourceUrl='http://example.org']){
  const b=sample();mutate(b.records[0]);assert.throws(()=>validatePublishedBundle(b,now+2000));
 }
});
test('partial row expiry never permits an expired or future published packet',()=>{
 assert.throws(()=>validatePublishedBundle(sample(),now+60000),/expired_or_future/);
 assert.throws(()=>validatePublishedBundle(sample(),now-1),/expired_or_future/);
});
test('refuse one source identity shared by unrelated streets before publication',()=>{
 const b=sample();b.records[0].officialCityId='source-city';
 b.records.push({...b.records[0],id:'other-house',street:'Інша вулиця',houses:['2'],queue:'2.1'});
 assert.throws(()=>validateBundle(b,now),/official_identity_spans_different_streets/);
 b.records[1].officialCityId='source-city:other-street';assert.doesNotThrow(()=>validateBundle(b,now));
});
test('refuse expired and mixed subscriber queue records',()=>{const b=sample();b.records[0].expiresAt=now-1;assert.throws(()=>validateBundle(b,now));});
test('refuse street extrapolation',()=>{const b=sample();b.records[0].scope='street';assert.throws(()=>validateBundle(b,now));});
test('refuse duplicate records',()=>{const b=sample();b.records.push({...b.records[0]});assert.throws(()=>validateBundle(b,now));});
test('refuse non-HTTPS source',()=>{const b=sample();b.records[0].sourceUrl='http://example.org';assert.throws(()=>validateBundle(b,now));});
import {mergeSnapshots,compactSnapshot} from '../snapshots.mjs';
test('source list and notation quotes survive compaction unchanged instead of becoming synthesized lists',()=>{
 const b=sample();b.records[0].quoteType='official-source-list-members';b.records[0].quote='Source house field: 1|3; selected member:1; GPV1.1';
 b.records.push({...b.records[0],id:'notation',houses:['2'],quoteType:'official-source-notation',quote:'Current source road: пров 2-й Зразковий; GPV1.1'});
 assert.deepEqual(compactSnapshot(b),b);
});
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
