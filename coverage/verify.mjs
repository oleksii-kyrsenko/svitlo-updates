import {readFile} from 'node:fs/promises';import {createPublicKey,verify} from 'node:crypto';import {hash,validateBundle,BASE} from './build.mjs';
const directory=process.argv[2]||'dynamic-coverage',now=Date.now();const envelope=JSON.parse(await readFile(directory+'/manifest.json'));
if(envelope.schemaVersion!==1||envelope.keyId!=='coverage-v1')throw Error('invalid_envelope');
const payload=Buffer.from(envelope.payload,'base64'),signature=Buffer.from(envelope.signature,'base64');const publicKey=createPublicKey(await readFile(new URL('./public.pem',import.meta.url)));
if(!verify(null,payload,publicKey,signature))throw Error('signature_invalid');const manifest=JSON.parse(payload);
if(manifest.schemaVersion!==1||manifest.generatedAt>now||manifest.expiresAt<=now||manifest.expiresAt>manifest.generatedAt+86400000||!Number.isSafeInteger(manifest.revision))throw Error('manifest_invalid_or_expired');
let records=0;for(const entry of manifest.bundles){if(entry.url!==BASE+'bundles/'+entry.sha256+'.json')throw Error('untrusted_bundle_url');const bytes=await readFile(directory+'/bundles/'+entry.sha256+'.json');if(hash(bytes)!==entry.sha256||bytes.length!==entry.size)throw Error('bundle_integrity');const b=validateBundle(JSON.parse(bytes),now);if(b.operatorId!==entry.operatorId||b.expiresAt!==entry.expiresAt)throw Error('bundle_metadata');records+=b.records.length;}
console.log(JSON.stringify({verified:true,revision:manifest.revision,operators:manifest.bundles.length,records}));
