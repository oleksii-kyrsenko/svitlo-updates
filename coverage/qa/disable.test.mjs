import test from 'node:test';import assert from 'node:assert/strict';
import {generateKeyPairSync,sign,verify} from 'node:crypto';
import {prepareDisableEnvelopes} from '../disable.mjs';
const {privateKey,publicKey}=generateKeyPairSync('ed25519');
function signed(schemaVersion,revision){const bytes=Buffer.from(JSON.stringify({schemaVersion,minClientVersion:schemaVersion,revision}));return {schemaVersion,keyId:'coverage-v1',payload:bytes.toString('base64'),signature:sign(null,bytes,privateKey).toString('base64')};}
test('disable signs both protocols with one revision higher than either previous generation',()=>{
 const result=prepareDisableEnvelopes({previousEnvelopes:[signed(1,20),signed(2,34)],privateKey,trustedPublicKey:publicKey,now:1000});assert.equal(result.revision,35);
 for(const e of result.envelopes){const bytes=Buffer.from(e.payload,'base64'),value=JSON.parse(bytes);assert(verify(null,bytes,publicKey,Buffer.from(e.signature,'base64')));assert.equal(value.revision,35);assert.equal(value.enabled,false);assert.deepEqual(value.bundles,[]);assert.equal(value.expiresAt,86401000);assert.equal(value.minClientVersion,e.schemaVersion);}
});
test('a corrupt old manifest or wrong key cannot partially prepare a disable',()=>{
 const old=signed(2,99);old.payload=Buffer.from('{"revision":1}').toString('base64');assert.throws(()=>prepareDisableEnvelopes({previousEnvelopes:[signed(1,20),old],privateKey,trustedPublicKey:publicKey,now:1000}),/unverified/);
 const other=generateKeyPairSync('ed25519');assert.throws(()=>prepareDisableEnvelopes({previousEnvelopes:[],privateKey:other.privateKey,trustedPublicKey:publicKey,now:1000}),/wrong_signing_key/);
});
test('upgrading an existing v1 channel creates an explicit v2 disable too',()=>{
 const result=prepareDisableEnvelopes({previousEnvelopes:[signed(1,88),null],privateKey,trustedPublicKey:publicKey,now:1000});assert.equal(result.revision,89);assert.equal(result.envelopes[1].schemaVersion,2);
});
