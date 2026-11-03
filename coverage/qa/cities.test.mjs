import test from 'node:test';
import assert from 'node:assert/strict';
import {cityShards,validateCityShard} from '../build-v2.mjs';
import {collectionPlan,collectorCommand} from '../collector-registry.mjs';
import {mergeSnapshots} from '../snapshots.mjs';
const now=100000,expiresAt=now+100000;
const row=(extra={})=>({id:'a',official:true,regionId:'UA-30',settlement:'м. Київ',community:'Київ',street:'вул. Зразкова',scope:'house',houses:['14-А'],queue:'2.1',sourceUrl:'https://example.org/official',quote:'м. Київ, вул. Зразкова, буд. 14-А: черга 2.1',checkedAt:now,expiresAt,...extra});
const packet=(records,operatorId='dtek-kyiv')=>({schemaVersion:1,operatorId,generatedAt:now,expiresAt,records});
const city={cityId:'osm-relation-421866',regionId:'UA-30',settlement:'Київ',community:'Київ',regionUnique:true,sourceUrl:'https://example.org/geography',checkedAt:now};
test('city shards separate geography and source street selectors, never renew rows',()=>{
 const [b]=cityShards([packet([row({officialCityId:'м. Київ',providerCityId:'10',providerStreetId:'20'})])],{now,geography:{cities:[city]}});
 assert.equal(b.cityId,city.cityId);assert.equal(b.records[0].officialCityId,undefined);assert.equal(b.records[0].providerStreetId,'20');assert.equal(b.records[0].checkedAt,now);assert.equal(b.records[0].expiresAt,expiresAt);assert.equal(b.geoCheckedAt,now);assert.doesNotThrow(()=>validateCityShard(b,now));
});
test('a partial city publication never asserts uniqueness without sourced geography',()=>{
 const [b]=cityShards([packet([row({officialCityId:'м. Київ'})])],{now});assert.equal(b.regionUnique,undefined);assert.equal(b.records[0].providerStreetId,undefined);
});
test('different communities with the same locality label remain distinct shards',()=>{
 const rows=[row({community:'Перша громада'}),row({id:'b',community:'Друга громада'})];assert.equal(cityShards([packet(rows)],{now}).length,2);
});
test('a city shard cannot contain another city or renewed assignments',()=>{
 const [b]=cityShards([packet([row()])],{now});b.records[0].settlement='Інше місто';assert.throws(()=>validateCityShard(b,now),/boundary/);
});
test('capital traversal uses sourced target with full bounded cursor, other regions stay active',()=>{
 const ops=[{id:'lviv',regionIds:['UA-46']},{id:'luhansk',regionIds:['UA-44']}],plan=collectionPlan(ops,[{settlement:'Львів',regionId:'UA-46'}],null,{requestLimit:300});
 assert.equal(plan.length,2);assert(plan[0].args.includes('--full-city'));assert(plan[0].args.includes('Львів'));assert(!plan[1].args.includes('--target-city'));
 assert.throws(()=>collectorCommand('lviv',{targetCity:'Львів',requestLimit:2001}),/invalid_city_request/);
});
test('a newly observed unknown house removes its old queue without removing untouched houses',()=>{
 const old=packet([row({houses:['14-А','16']})]);const fresh={...packet([]),observedHouses:[{regionId:'UA-30',settlement:'м. Київ',community:'Київ',street:'вул. Зразкова',house:'14-А'}]};
 const result=mergeSnapshots(old,fresh,now);assert.deepEqual(result.records[0].houses,['16']);assert.equal(result.records[0].expiresAt,expiresAt);
});
test('capital priority preserves a separate scheduled all-settlement cursor mode',()=>{
 const ops=[{id:'ternopil',regionIds:['UA-61']}],cities=[{settlement:'Тернопіль',regionId:'UA-61'}];
 const capital=collectionPlan(ops,cities,null,{requestLimit:100})[0];assert.equal(capital.args[0],'coverage/collect-official-bulk.py');assert(capital.args.includes('--full-city'));
 const global=collectionPlan(ops,cities,null,{capitalPriority:false})[0];assert.equal(global.args[0],'coverage/collect-batch-b.py');assert(!global.args.includes('--target-city'));assert.equal(global.targetCity,null);
});
