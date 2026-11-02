import test from 'node:test';import assert from 'node:assert/strict';
import {mkdtemp,mkdir,readFile,writeFile,stat} from 'node:fs/promises';import {tmpdir} from 'node:os';
import {rebuildFromStaging} from '../rebuild-from-staging.mjs';import {hash} from '../build.mjs';
const now=100000,expiresAt=200000;
const row={id:'training',official:true,regionId:'UA-46',settlement:'Навчальне',community:'Навчальна громада',street:'Нова',scope:'house',houses:['1-А'],queue:'1.1',sourceUrl:'https://example.org/source',quote:'Навчальне, Нова, будинок1-А: черга1.1',checkedAt:now,expiresAt};
async function workspace(){const root=await mkdtemp(tmpdir()+'/rebuild-staging-');await mkdir(root+'/staging');return {root,out:root+'/publication',staging:root+'/staging',reportFile:root+'/report.json',now};}
test('dry rebuild fingerprints known source staging without network, key, index writes or timestamp renewal',async()=>{
 const args=await workspace(),bytes=Buffer.from(JSON.stringify({schemaVersion:1,operatorId:'lviv',generatedAt:now,expiresAt,records:[row]}));await writeFile(args.staging+'/lviv.json',bytes);
 await writeFile(args.staging+'/volyn.json',JSON.stringify({operatorId:'somebody-else'}));
 const report=await rebuildFromStaging({...args,dryRun:true});assert.equal(report.inputs.length,1);assert.equal(report.inputs[0].sha256,hash(bytes));assert.equal(report.inputs[0].generatedAt,now);assert.equal(report.proposedSourceOperators,1);assert.equal(report.proposedSourceRecords,1);assert.equal(report.errors[0].error,'staging_operator_mismatch');
 assert.deepEqual(await readFile(args.staging+'/lviv.json'),bytes);await assert.rejects(()=>stat(args.out+'/manifest.json'),{code:'ENOENT'});
});
test('missing signing key retains the original files and writes a diagnostic rather than an unsigned fallback',async()=>{
 const args=await workspace();await writeFile(args.staging+'/lviv.json',JSON.stringify({schemaVersion:1,operatorId:'lviv',generatedAt:now,expiresAt,records:[row]}));
 await assert.rejects(()=>rebuildFromStaging({...args,keyFile:null}),/Signing secret unavailable/);assert.equal(JSON.parse(await readFile(args.reportFile)).signing,'missing_key_previous_indexes_preserved');await assert.rejects(()=>stat(args.out+'/manifest.json'),{code:'ENOENT'});
});
test('an expired or private-field source cannot become a newly dated signed assignment',async()=>{
 const args=await workspace();await writeFile(args.staging+'/lviv.json',JSON.stringify({schemaVersion:1,operatorId:'lviv',generatedAt:now,expiresAt,records:[{...row,accountId:'private'}]}));
 await assert.rejects(()=>rebuildFromStaging({...args,dryRun:true}),/no_valid_source_snapshots/);const report=JSON.parse(await readFile(args.reportFile));assert.equal(report.errors[0].error,'fresh_snapshot_invalid_previous_unexpired_preserved');assert.equal(report.proposedSourceRecords,0);
});
