import test from 'node:test';import assert from 'node:assert/strict';
import {cityShards,validateCityShard} from '../build-v2.mjs';
const now=100000,expiresAt=200000;
const row=(extra={})=>({id:'a',official:true,regionId:'UA-30',settlement:'Київ',community:'Київ',street:'вул. Зразкова',scope:'house',houses:['14-А'],queue:'2.1',sourceUrl:'https://example.org/official',quote:'Київ, вул. Зразкова, буд. 14-А: черга 2.1',providerCityId:'city-7',providerStreetId:'street-2',checkedAt:now,expiresAt,...extra});
const packet=records=>({schemaVersion:1,operatorId:'example',generatedAt:now,expiresAt,records});
test('uniform provider city is declared separately and mixed IDs are not invented',()=>{
 const [known]=cityShards([packet([row()])],{now});assert.equal(known.providerCityId,'city-7');validateCityShard(known,now);
 const [mixed]=cityShards([packet([row(),row({id:'b',providerCityId:'city-8',providerStreetId:'street-3'})])],{now});assert.equal(mixed.providerCityId,undefined);
 const [legacy]=cityShards([packet([row({providerCityId:undefined})])],{now});assert.equal(legacy.providerCityId,undefined);
});
test('publisher refuses contradictory provider city, street selectors and unsourced identity assertions',()=>{
 for(const mutate of [b=>b.records[0].providerCityId='other',b=>b.records[0].officialCityId='legacy-city',b=>b.regionUnique=true,b=>b.geoCheckedAt=now+1,b=>b.records.push({...b.records[0],id:'b',street:'Інша вулиця'})]){
  const [b]=cityShards([packet([row()])],{now});mutate(b);assert.throws(()=>validateCityShard(b,now));
 }
});
test('explicit source city codes survive sharding and cannot be silently overwritten by metadata',()=>{
 const katottg='UA12345678901234567';const [b]=cityShards([packet([row({katottg})])],{now});assert.equal(b.katottg,katottg);assert.equal(b.records[0].katottg,katottg);validateCityShard(b,now);
 const geography={cities:[{cityId:'source-city',regionId:'UA-30',settlement:'Київ',community:'Київ',katottg:'UA00000000000000000'}]};
 assert.throws(()=>cityShards([packet([row({katottg})])],{now,geography}),/source_city_code_conflict/);
});
