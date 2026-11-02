import {readFile} from 'node:fs/promises';
import {createPublicKey,verify} from 'node:crypto';
import {CITY_BASE,validateCityShard} from './build-v2.mjs';
import {hash} from './build.mjs';
import {readSourceSnapshots} from './publisher-snapshots.mjs';
const out=process.argv[2]||'dynamic-coverage/v2',now=Date.now();
const env=JSON.parse(await readFile(out+'/manifest.json')),key=createPublicKey(await readFile(new URL('./public.pem',import.meta.url))),bytes=Buffer.from(env.payload||'','base64');
if(env.schemaVersion!==2||env.keyId!=='coverage-v1'||!verify(null,bytes,key,Buffer.from(env.signature||'','base64')))throw Error('city_signature_invalid');
const m=JSON.parse(bytes);
if(m.schemaVersion!==2||m.minClientVersion!==2||!m.enabled||!Number.isSafeInteger(m.revision)||m.revision<1||m.generatedAt>now||m.expiresAt<=now||m.expiresAt>m.generatedAt+86400000||!Array.isArray(m.bundles))throw Error('city_manifest_invalid');
const ids=new Set();let records=0;
for(const e of m.bundles){
 const id=e.operatorId+'/'+e.cityId;if(ids.has(id)||!/^[a-f0-9]{64}$/.test(e.sha256)||e.url!==CITY_BASE+'bundles/'+e.sha256+'.json'||!Number.isInteger(e.size)||e.size<1||e.size>8*1024*1024||!Number.isFinite(e.expiresAt)||e.expiresAt<=m.generatedAt||e.expiresAt>m.expiresAt)throw Error('city_descriptor_invalid');ids.add(id);
 const raw=await readFile(out+'/bundles/'+e.sha256+'.json');if(raw.length!==e.size||hash(raw)!==e.sha256)throw Error('city_bundle_integrity');
 const b=JSON.parse(raw);validateCityShard(b,b.generatedAt);if(b.generatedAt>now||b.expiresAt<=now||b.expiresAt>b.generatedAt+86400000)throw Error('city_bundle_expired');for(const k of ['cityId','operatorId','regionId','settlement','community','katottg','providerCityId','regionUnique','geoSourceUrl','geoCheckedAt','expiresAt'])if(b[k]!==e[k])throw Error('city_bundle_metadata');records+=b.records.length;
}
for(const e of m.retiredCities||[]){const id=e.operatorId+'/'+e.cityId;if(ids.has(id))throw Error('duplicate_retired_city');ids.add(id);}
const sources=await readSourceSnapshots(m,out,now);
console.log(JSON.stringify({verified:true,protocol:2,revision:m.revision,cities:m.bundles.length,records,sourceSnapshots:sources.length}));
