// Source-side publisher. Only public data and this standalone collector belong here.
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {createHash,createPrivateKey,sign,verify,createPublicKey} from 'node:crypto';
import {pathToFileURL} from 'node:url';
export const BASE='https://raw.githubusercontent.com/oleksii-kyrsenko/svitlo-updates/main/dynamic-coverage/';
export const hash=data=>createHash('sha256').update(data).digest('hex');
const https=value=>{try{const u=new URL(value);return u.protocol==='https:'&&!u.username&&!u.password&&!u.hash;}catch{return false;}};
export function validateBundle(b,now=Date.now()){
 if(b?.schemaVersion!==1||!/^[-a-z0-9]+$/.test(b.operatorId)||!Number.isFinite(b.generatedAt)||b.generatedAt>now||now-b.generatedAt>86400000||!Number.isFinite(b.expiresAt)||b.expiresAt<=now||b.expiresAt>b.generatedAt+86400000||!Array.isArray(b.records)||!b.records.length||b.records.length>100000)throw Error('invalid_bundle');
 const allowed=new Set(['id','official','regionId','settlement','community','street','scope','houses','houseRanges','excludedHouses','queue','sourceUrl','quote','quoteType','publishedAt','checkedAt','expiresAt','officialCityId','katottg']);
 const ids=new Set();for(const r of b.records){
  if(Object.keys(r).some(k=>!allowed.has(k)))throw Error('unexpected_record_field');
  if(!r||typeof r.id!=='string'||ids.has(r.id)||r.official!==true||!/^UA-\d\d$/.test(r.regionId)||!r.settlement||typeof r.community!=='string'||!['house','street','settlement'].includes(r.scope)||!/^\d{1,2}(?:\.\d{1,2})?$/.test(r.queue)||!https(r.sourceUrl)||typeof r.quote!=='string'||r.quote.length<3||r.quote.length>2500||!Number.isFinite(r.checkedAt)||r.checkedAt>now||!Number.isFinite(r.expiresAt)||r.expiresAt<=now||r.expiresAt>r.checkedAt+86400000)throw Error('invalid_record');
  if(r.scope!=='settlement'&&!r.street)throw Error('missing_street');
  if(r.scope==='house'&&(!Array.isArray(r.houses)||!r.houses.length||r.houses.some(h=>typeof h!=='string'||!h.trim())))throw Error('missing_houses');
  if(r.scope==='street'&&!/вся вулиця|усі будинки|всі будинки/iu.test(r.quote))throw Error('unbounded_street');
  if(r.scope==='settlement'&&!/весь населений пункт|усе село|все село|усе селище|все селище/iu.test(r.quote))throw Error('unbounded_settlement');
  ids.add(r.id);
 }
 return b;
}
export async function build({catalog,bundles,revision,keyFile,out,now=Date.now()}){
 if(!Number.isSafeInteger(revision)||revision<1)throw Error('invalid_revision');
 if(catalog?.schemaVersion!==1||!Array.isArray(catalog.operators)||catalog.operators.length<1||catalog.operators.length>100||catalog.expiresAt<=now||catalog.expiresAt>now+86400000)throw Error('invalid_catalog');
 const operators=new Set();for(const o of catalog.operators){if(!/^[-a-z0-9]+$/.test(o.id)||operators.has(o.id)||!o.name||!https(o.sourceUrl)||!Array.isArray(o.regionIds))throw Error('invalid_operator');operators.add(o.id);}
 const privateKey=createPrivateKey(await readFile(keyFile));const publicKey=createPublicKey(privateKey),descriptors=[],ids=new Set();
 const trusted=createPublicKey(await readFile(new URL('./public.pem',import.meta.url))).export({type:'spki',format:'der'});
 if(!publicKey.export({type:'spki',format:'der'}).equals(trusted))throw Error('signing_key_does_not_match_client_pin');await mkdir(out+'/bundles',{recursive:true});
 for(const bundle of bundles){validateBundle(bundle,now);if(!operators.has(bundle.operatorId)||ids.has(bundle.operatorId))throw Error('unknown_or_duplicate_operator');ids.add(bundle.operatorId);const bytes=Buffer.from(JSON.stringify(bundle)+'\n');if(bytes.length>8*1024*1024)throw Error('oversize_bundle');const sha256=hash(bytes);await writeFile(out+'/bundles/'+sha256+'.json',bytes);descriptors.push({operatorId:bundle.operatorId,url:BASE+'bundles/'+sha256+'.json',sha256,size:bytes.length,expiresAt:bundle.expiresAt});}
 if(!descriptors.length)throw Error('empty_publication');
 const payload=Buffer.from(JSON.stringify({schemaVersion:1,revision,generatedAt:now,expiresAt:Math.min(now+86400000,catalog.expiresAt,Math.max(...bundles.map(b=>b.expiresAt))),minClientVersion:1,enabled:true,catalog,bundles:descriptors}));
 const signature=sign(null,payload,privateKey);if(!verify(null,payload,publicKey,signature))throw Error('self_verification_failed');const envelope={schemaVersion:1,keyId:'coverage-v1',payload:payload.toString('base64'),signature:signature.toString('base64')};
 await writeFile(out+'/manifest.json',JSON.stringify(envelope,null,2)+'\n');return {revision,operators:descriptors.length,records:bundles.reduce((a,b)=>a+b.records.length,0)};
}
if(import.meta.url===pathToFileURL(process.argv[1]||'').href){
 const [catalogFile,bundleFiles,keyFile,out,rev]=process.argv.slice(2);if(!rev)throw Error('Usage: node coverage/build.mjs catalog.json bundles.json-list private-key.pem output-dir revision');
 const catalog=JSON.parse(await readFile(catalogFile)),files=JSON.parse(await readFile(bundleFiles));const bundles=await Promise.all(files.map(async f=>JSON.parse(await readFile(f))));console.log(JSON.stringify(await build({catalog,bundles,keyFile,out,revision:Number(rev)})));
}
