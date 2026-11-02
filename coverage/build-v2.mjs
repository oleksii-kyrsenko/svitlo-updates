// Versioned city shards. The legacy v1 publication remains available to build88.
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {createPrivateKey,createPublicKey,sign,verify} from 'node:crypto';
import {hash,validateBundle} from './build.mjs';
import {storeSourceSnapshots} from './publisher-snapshots.mjs';
export const CITY_BASE='https://raw.githubusercontent.com/oleksii-kyrsenko/svitlo-updates/main/dynamic-coverage/v2/';
const day=86400000;
const locality=s=>String(s||'').normalize('NFKC').toLocaleLowerCase('uk').replace(/^(?:м\.|с\.|г\.|місто\s|село\s|селище\s|смт\.?\s|с-ще\s)\s*/u,'').replace(/[’ʼ`']/g,'').replace(/\s+/g,' ').trim();
const community=s=>locality(s).split(' ').filter(w=>!['територіальна','міська','селищна','сільська','громада','громади'].includes(w)).join(' ');
const https=s=>{try{const u=new URL(s);return u.protocol==='https:'&&!u.username&&!u.password&&!u.hash;}catch{return false;}};
export function shardCity(record,geography){
 const matches=(geography?.cities||[]).filter(c=>c.regionId===record.regionId&&locality(c.settlement)===locality(record.settlement)&&(!c.community||community(c.community)===community(record.community)));
 const c=matches.length===1?matches[0]:null;
 if(c?.katottg&&record.katottg&&String(c.katottg)!==String(record.katottg))throw Error('source_city_code_conflict');
 const cityId=c?.cityId||'locality-'+hash(JSON.stringify([record.regionId,locality(record.settlement),community(record.community),...(record.katottg?[String(record.katottg)]:[])])).slice(0,24);
 return {cityId,regionId:record.regionId,settlement:c?.settlement||record.settlement,community:c?.community||record.community,...(c?.katottg||record.katottg?{katottg:String(c?.katottg||record.katottg)}:{}),...(c?.regionUnique===true&&https(c.sourceUrl)&&Number.isFinite(c.checkedAt)?{regionUnique:true,geoSourceUrl:c.sourceUrl,geoCheckedAt:c.checkedAt}:{} )};
}
export function cityShards(bundles,{geography,now=Date.now()}={}){
 const shards=new Map();
 for(const raw of bundles){
  validateBundle(raw,now);
  for(const r of raw.records){
   const city=shardCity(r,geography),key=raw.operatorId+'|'+city.cityId;
   if(!shards.has(key))shards.set(key,{schemaVersion:2,operatorId:raw.operatorId,...city,generatedAt:now,expiresAt:now,records:[]});
   const b=shards.get(key),{officialCityId,...record}=r;
   if((b.katottg||'')!==(city.katottg||''))throw Error('source_city_code_conflict');
   record.settlement=b.settlement;record.community=b.community;if(b.katottg)record.katottg=b.katottg;
   // The historical field overloaded city/street identities. Keep only a true
   // known street selector; DTEK/YASNO legacy selectors are never inferred.
   if(!record.providerStreetId&&officialCityId&&!raw.operatorId.startsWith('dtek-')&&raw.operatorId!=='cek')record.providerStreetId=officialCityId;
   b.records.push(record);b.expiresAt=Math.max(b.expiresAt,r.expiresAt);
  }
 }
 for(const b of shards.values()){
  const cityIds=new Set(b.records.map(r=>r.providerCityId));
  if(cityIds.size===1&&!cityIds.has(undefined))b.providerCityId=[...cityIds][0];
 }
 return [...shards.values()];
}
export function validateCityShard(b,now=Date.now()){
 if(b?.schemaVersion!==2||typeof b.cityId!=='string'||b.cityId.length>150||!/^[-a-z0-9]+$/.test(b.cityId)||typeof b.operatorId!=='string'||b.operatorId.length>150||!/^[-a-z0-9]+$/.test(b.operatorId)||!/^UA-\d\d$/.test(b.regionId)||!b.settlement||!b.community)throw Error('invalid_city_shard');
 if(b.geoSourceUrl!==undefined&&!https(b.geoSourceUrl))throw Error('invalid_city_geography_source');
 if(b.geoCheckedAt!==undefined&&(!Number.isFinite(b.geoCheckedAt)||b.geoCheckedAt<=0||b.geoCheckedAt>b.generatedAt))throw Error('invalid_city_geography_time');
 if(b.regionUnique!==undefined&&typeof b.regionUnique!=='boolean')throw Error('invalid_city_uniqueness');
 if(b.regionUnique===true&&(!https(b.geoSourceUrl)||!Number.isFinite(b.geoCheckedAt)||b.geoCheckedAt<=0||b.geoCheckedAt>b.generatedAt))throw Error('unsourced_city_uniqueness');
 if(b.katottg!==undefined&&!/^UA\d{17}$/.test(b.katottg))throw Error('invalid_city_katottg');
 if(b.providerCityId!==undefined&&(typeof b.providerCityId!=='string'||!b.providerCityId||b.providerCityId.length>150))throw Error('invalid_provider_city_id');
 const streetIds=new Map();
 const rows=b.records?.map(r=>{
  if(r.regionId!==b.regionId||locality(r.settlement)!==locality(b.settlement)||community(r.community)!==community(b.community))throw Error('record_crosses_city_boundary');
  if(r.providerCityId!==undefined&&(typeof r.providerCityId!=='string'||!r.providerCityId.length||r.providerCityId.length>150))throw Error('invalid_provider_city_id');
  if(r.providerStreetId!==undefined&&(typeof r.providerStreetId!=='string'||!r.providerStreetId.length||r.providerStreetId.length>150))throw Error('invalid_provider_street_id');
  if(r.officialCityId!==undefined)throw Error('legacy_selector_in_city_record');
  if((r.katottg||'')!==(b.katottg||''))throw Error('record_crosses_city_code');
  if(b.providerCityId!==undefined&&r.providerCityId!==b.providerCityId)throw Error('record_crosses_provider_city');
  if(r.providerStreetId&&r.street){const name=r.street.normalize('NFKC').toLocaleLowerCase('uk').replace(/\s+/g,' ').trim();if(streetIds.has(r.providerStreetId)&&streetIds.get(r.providerStreetId)!==name)throw Error('provider_identity_spans_streets');streetIds.set(r.providerStreetId,name);}
  const {providerCityId,providerStreetId,...v1}=r;return v1;
 });
 validateBundle({...b,schemaVersion:1,records:rows},now);return b;
}
function cityIdentity(entry){return JSON.stringify([entry.operatorId,entry.cityId]);}
function tombstone(entry){const {url,sha256,size,expiresAt,...city}=entry;return city;}
export async function buildCityCoverage({bundles,catalog,revision,keyFile,out,geography,now=Date.now(),previousManifest=null,allowEmptyPublication=false}){
 if(!Number.isSafeInteger(revision)||revision<1)throw Error('invalid_revision');
 const key=createPrivateKey(await readFile(keyFile)),pub=createPublicKey(key),trusted=createPublicKey(await readFile(new URL('./public.pem',import.meta.url)));
 if(!pub.export({type:'spki',format:'der'}).equals(trusted.export({type:'spki',format:'der'})))throw Error('signing_key_does_not_match_client_pin');
 let previous=null;
 if(previousManifest){
  const bytes=Buffer.from(previousManifest.payload||'','base64');
  if(previousManifest.schemaVersion!==2||previousManifest.keyId!=='coverage-v1'||!verify(null,bytes,trusted,Buffer.from(previousManifest.signature||'','base64')))throw Error('unverified_previous_city_manifest');
  previous=JSON.parse(bytes);if(previous.schemaVersion!==2||previous.minClientVersion!==2||!Array.isArray(previous.bundles)||previous.revision>=revision)throw Error('city_revision_not_increasing');
 }
 if(!Number.isFinite(catalog?.expiresAt)||catalog.expiresAt<=now||catalog.expiresAt>now+day)throw Error('invalid_city_catalog_expiry');
 const shards=cityShards(bundles,{geography,now}),entries=[],skippedCities=[];let records=0;
 if(!shards.length&&!allowEmptyPublication)throw Error('empty_city_publication');
 await mkdir(out+'/bundles',{recursive:true});
 for(const b of shards){
  validateCityShard(b,now);const bytes=Buffer.from(JSON.stringify(b)+'\n');
  if(bytes.length>8*1024*1024){
   // A source can outgrow the phone's package ceiling. Keep the exact previous
   // authenticated city generation, if still live; never renew its observation
   // times, and never advertise a construction limit as an official withdrawal.
   const skipped={operatorId:b.operatorId,cityId:b.cityId,reason:'oversize_city_shard',bytes:bytes.length,previousRetained:false};
   const old=previous?.bundles.find(e=>cityIdentity(e)===cityIdentity(b));
   if(old&&old.expiresAt>now){
    try{
     if(!/^[a-f0-9]{64}$/.test(old.sha256)||old.url!==CITY_BASE+'bundles/'+old.sha256+'.json'||!Number.isInteger(old.size)||old.size<1||old.size>8*1024*1024)throw Error('invalid_previous_city_descriptor');
     const raw=await readFile(out+'/bundles/'+old.sha256+'.json');
     if(raw.length!==old.size||hash(raw)!==old.sha256)throw Error('previous_city_integrity');
     const saved=JSON.parse(raw);validateCityShard(saved,saved.generatedAt);
     if(saved.generatedAt>now||saved.expiresAt<=now||saved.expiresAt>saved.generatedAt+day)throw Error('previous_city_expired');
     for(const k of ['cityId','operatorId','regionId','settlement','community','katottg','providerCityId','regionUnique','geoSourceUrl','geoCheckedAt','expiresAt'])if(saved[k]!==old[k])throw Error('previous_city_metadata');
     entries.push(old);records+=saved.records.length;skipped.previousRetained=true;
    }catch{skipped.previousConstraint='previous_city_unavailable_or_invalid';}
   }
   skippedCities.push(skipped);continue;
  }
  const sha256=hash(bytes);await writeFile(out+'/bundles/'+sha256+'.json',bytes);
  const {records:rows,schemaVersion,generatedAt,...entry}=b;
  entries.push({...entry,url:CITY_BASE+'bundles/'+sha256+'.json',sha256,size:bytes.length});records+=rows.length;
 }
 if(!entries.length&&(!allowEmptyPublication||skippedCities.length))throw Error('no_supported_city_shards_previous_manifest_preserved');
 const active=new Set(entries.map(cityIdentity)),skippedIds=new Set(skippedCities.map(cityIdentity));let retiredCities=[];
 if(previous){
  const retired=new Map();for(const e of [...previous.bundles,...(previous.retiredCities||[])])if(!active.has(cityIdentity(e))&&!skippedIds.has(cityIdentity(e)))retired.set(cityIdentity(e),tombstone(e));retiredCities=[...retired.values()];
 }
 if(entries.length+retiredCities.length>5000)throw Error('city_index_limit');
 const sourceCache=await storeSourceSnapshots(bundles,out,now);
 const value={schemaVersion:2,minClientVersion:2,revision,enabled:true,generatedAt:now,expiresAt:Math.min(now+day,catalog.expiresAt,entries.length||sourceCache.descriptors.length?Math.max(...entries.map(e=>e.expiresAt),...sourceCache.descriptors.map(e=>e.expiresAt)):now+day),catalog,bundles:entries,retiredCities,sourceSnapshots:sourceCache.descriptors};
 const payload=Buffer.from(JSON.stringify(value));if(payload.length>2*1024*1024)throw Error('city_index_size_limit');
 const signature=sign(null,payload,key),envelope={schemaVersion:2,keyId:'coverage-v1',payload:payload.toString('base64'),signature:signature.toString('base64')};
 if(!verify(null,payload,pub,signature))throw Error('city_self_verification_failed');
 await writeFile(out+'/manifest.json',JSON.stringify(envelope,null,2)+'\n');
 return {revision,cities:entries.length,retiredCities:retiredCities.length,records,skippedCities,sourceSnapshots:sourceCache.descriptors.length,sourceCacheConstraints:sourceCache.skipped};
}
