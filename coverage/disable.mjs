import {readFile,writeFile} from 'node:fs/promises';import {createPrivateKey,createPublicKey,sign} from 'node:crypto';
const keyFile=process.env.DYNAMIC_COVERAGE_KEY_FILE;if(!keyFile)throw Error('Set DYNAMIC_COVERAGE_KEY_FILE to protected signing file');
const privateKey=createPrivateKey(await readFile(keyFile)),trusted=createPublicKey(await readFile(new URL('./public.pem',import.meta.url)));
if(!createPublicKey(privateKey).export({type:'spki',format:'der'}).equals(trusted.export({type:'spki',format:'der'})))throw Error('wrong_signing_key');
const file='dynamic-coverage/manifest.json',envelope=JSON.parse(await readFile(file));const previous=JSON.parse(Buffer.from(envelope.payload,'base64'));const now=Date.now();
const payload=Buffer.from(JSON.stringify({schemaVersion:1,minClientVersion:1,revision:previous.revision+1,enabled:false,generatedAt:now,expiresAt:now+86400000,bundles:[]}));
await writeFile(file,JSON.stringify({schemaVersion:1,keyId:'coverage-v1',payload:payload.toString('base64'),signature:sign(null,payload,privateKey).toString('base64')},null,2)+'\n');
console.log('Signed disable manifest prepared; commit/push after inspection.');
