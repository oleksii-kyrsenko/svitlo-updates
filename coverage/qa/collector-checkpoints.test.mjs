import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,mkdir,readFile,writeFile,rm,access} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {collectSourceCommand,combineSnapshots,refresh} from '../refresh.mjs';

const at=Date.UTC(2026,10,4,6),expiresAt=at+86400000;
const target={regionId:'UA-35',settlement:'Навчальне',community:'Навчальна громада'};
const operator={id:'kirovohrad',name:'Навчальний оператор',regionIds:['UA-35'],sourceUrl:'https://kiroe.com.ua/electricity-blackout'};
const row=(id,house,extra={})=>({id,official:true,...target,street:'вул. Навчальна',scope:'house',houses:[house],queue:'2.1',sourceUrl:operator.sourceUrl,quote:'Навчальне, вул. Навчальна, будинок '+house+': черга 2.1',checkedAt:at+1,expiresAt,officialCityId:'city:read',...extra});
const packet=()=>({schemaVersion:1,operatorId:operator.id,generatedAt:at+3,expiresAt,records:[row('fresh','1')],observedHouses:[{...target,street:'вул. Навчальна',house:'2',checkedAt:at+2,expiresAt}],completedStreetIds:['city:read','city:unread']});
const absent=async file=>{try{await access(file);return false;}catch(error){if(error.code==='ENOENT')return true;throw error;}};
async function fixture(run){
 const directory=await mkdtemp(join(tmpdir(),'coverage-checkpoint-'));
 const output=join(directory,'packet.json'),state=join(directory,'cursor.json');
 const command={operatorId:operator.id,targetCity:target.settlement,fullCity:true,output,args:['coverage/collect-city-forms.py','--output',output,'--state',state]};
 const original=JSON.stringify({streetIndex:4});await writeFile(state,original);
 try{return await run({directory,output,state,command,original});}finally{await rm(directory,{recursive:true,force:true});}
}
function killed(){return Object.assign(Error('request details must not enter the report'),{killed:true});}

test('a killed collector recovers only its newly written completed-house checkpoint and preserves the source error',async()=>fixture(async({output,state,command})=>{
 await writeFile(output,JSON.stringify({...packet(),generatedAt:at-10}));await writeFile(output+'.report.json',JSON.stringify({records:999999}));let now=at;
 const result=await collectSourceCommand(command,{operator,target,clock:()=>now,runner:async()=>{
  assert(await absent(output));assert(await absent(output+'.report.json'));
  await writeFile(output,JSON.stringify(packet()));await writeFile(state,JSON.stringify({streetIndex:5}));now=at+10;throw killed();
 }});
 assert.equal(result.error,'collector_timeout');assert.equal(result.checkpointRecovered,true);assert.equal(result.collection.status,'collected_checkpoint');assert.equal(result.collection.records,1);
 assert.deepEqual(JSON.parse(await readFile(state)),{streetIndex:5});
 assert.equal(result.snapshot.records[0].checkedAt,at+1);assert.equal(result.snapshot.records[0].expiresAt,expiresAt);
 assert.equal(result.snapshot.observedHouses[0].checkedAt,at+2);assert.equal(result.snapshot.observedHouses[0].expiresAt,expiresAt);
 assert.deepEqual(result.snapshot.completedStreetIds,[]);assert.equal(result.snapshot.completeSnapshot,undefined);
 const old={schemaVersion:1,operatorId:operator.id,generatedAt:at-10,expiresAt:expiresAt-10,records:[row('old','1',{queue:'1.1',checkedAt:at-10,expiresAt:expiresAt-10,houses:['1','2','3']}),row('unread','4',{queue:'1.1',checkedAt:at-10,expiresAt:expiresAt-10,officialCityId:'city:unread',street:'вул. Інша'})]};
 const combined=combineSnapshots([old],[result.snapshot],at+10);assert.deepEqual(combined.errors,[]);
 const houses=combined.bundles[0].records.flatMap(r=>r.houses);assert.deepEqual(houses.sort(),['1','3','4']);
 assert.equal(combined.bundles[0].records.find(r=>r.houses.includes('1')).queue,'2.1');
 assert.equal(combined.sourceSnapshots[0].negativeHouseWatermarks[0].checkedAt,at+2);
}));

test('stale, malformed, cross-operator, private, wrong-source and unbounded checkpoint data restore the pre-run cursor',async t=>{
 const variants={
  'stale invocation':p=>({...p,generatedAt:at-1}),
  'old observation under a new packet timestamp':p=>({...p,records:[{...p.records[0],checkedAt:at-1}]}),
  'different operator':p=>({...p,operatorId:'volyn'}),
  'different city':p=>({...p,records:[{...p.records[0],settlement:'Інше'}]}),
  'different official host':p=>({...p,records:[{...p.records[0],sourceUrl:'https://other.example/official'}]}),
  'invalid positive queue':p=>({...p,records:[{...p.records[0],queue:'unknown'}]}),
  'expired observation':p=>({...p,observedHouses:[{...p.observedHouses[0],expiresAt:at}]}),
  'implicit negative observation time':p=>({...p,observedHouses:[{...p.observedHouses[0],checkedAt:undefined}]}),
  'private observation field':p=>({...p,observedHouses:[{...p.observedHouses[0],account:'private'}]}),
  'full operator withdrawal':p=>({...p,completeSnapshot:true}),
  'unqualified street coverage':p=>({...p,records:[{...p.records[0],scope:'street',quote:'вся вулиця Навчальна'}]}),
  'malformed JSON':()=>'{incomplete JSON',
 };
 for(const [name,change] of Object.entries(variants))await t.test(name,async()=>fixture(async({output,state,command,original})=>{
  let now=at;const result=await collectSourceCommand(command,{operator,target,clock:()=>now,runner:async()=>{const value=change(packet());await writeFile(output,typeof value==='string'?value:JSON.stringify(value));await writeFile(state,'{"streetIndex":5}');now=at+10;throw killed();}});
  assert.equal(result.snapshot,null);assert.equal(result.checkpointRejected,true);assert.equal(result.error,'collector_timeout');assert.equal(result.collection.status,'not_collected');assert.equal(await readFile(state,'utf8'),original);
 }));
});

test('a failure before any new checkpoint cannot ingest an earlier packet or retain its advanced cursor',async()=>fixture(async({output,state,command,original})=>{
 await writeFile(output,JSON.stringify(packet()));
 const result=await collectSourceCommand(command,{operator,target,clock:()=>at,runner:async()=>{await writeFile(state,'{"streetIndex":5}');throw killed();}});
 assert.equal(result.snapshot,null);assert.equal(result.checkpointRecovered,false);assert.equal(await readFile(state,'utf8'),original);
}));

test('a nonzero exit can retain explicit all-negative observations without inventing a queue or renewing their age',async()=>fixture(async({output,command})=>{
 let now=at;const fresh={...packet(),records:[]};
 const result=await collectSourceCommand(command,{operator,target,clock:()=>now,runner:async()=>{await writeFile(output,JSON.stringify(fresh));now=at+10;throw Object.assign(Error('source HTTP failure'),{code:1});}});
 assert.equal(result.error,'collector_failed');assert.equal(result.checkpointRecovered,true);assert.equal(result.collection.records,0);
 const combined=combineSnapshots([],[result.snapshot],now);assert.deepEqual(combined.errors,[]);assert.deepEqual(combined.bundles,[]);
 assert.equal(combined.sourceSnapshots[0].negativeHouseWatermarks[0].checkedAt,at+2);assert.equal(combined.sourceSnapshots[0].negativeHouseWatermarks[0].expiresAt,expiresAt);
}));

test('successful complete-street reads retain the normal authoritative-street semantics',async()=>fixture(async({output,state,command})=>{
 let now=at;const result=await collectSourceCommand(command,{operator,target,clock:()=>now,runner:async()=>{await writeFile(output,JSON.stringify(packet()));await writeFile(state,'{"streetIndex":5}');now=at+10;}});
 assert.equal(result.error,null);assert.equal(result.collection.status,'collected');assert.deepEqual(result.snapshot.completedStreetIds,packet().completedStreetIds);assert.equal(result.checkpointRecovered,false);
 assert.equal(JSON.parse(await readFile(state)).streetIndex,5);
}));

test('a malformed normal-success packet also rolls its cursor back',async()=>fixture(async({output,state,command,original})=>{
 const result=await collectSourceCommand(command,{operator,target,clock:()=>at,runner:async()=>{await writeFile(output,'{}');await writeFile(state,'{"streetIndex":5}');}});
 assert.equal(result.snapshot,null);assert.equal(result.error,'collector_output_invalid');assert.equal(await readFile(state,'utf8'),original);
}));

test('failed collectors without atomic city checkpoints keep their original failure path',async()=>fixture(async({output,command})=>{
 const other={...command,args:['coverage/batch-a.py','--output',output]};
 const result=await collectSourceCommand(other,{operator,target,clock:()=>at+10,runner:async()=>{await writeFile(output,JSON.stringify(packet()));throw killed();}});
 assert.equal(result.snapshot,null);assert.equal(result.error,'collector_timeout');assert.equal(result.rollbackCursor,null);
}));

test('missing signing key cannot commit a recovered checkpoint cursor ahead of signed facts',async()=>fixture(async({directory})=>{
 const previousCwd=process.cwd(),names=['COVERAGE_OPERATORS','COVERAGE_COLLECTION_MODE','DYNAMIC_COVERAGE_KEY_FILE'],environment=Object.fromEntries(names.map(name=>[name,process.env[name]]));
 await mkdir(join(directory,'coverage/cursors'),{recursive:true});await writeFile(join(directory,'coverage/sources.json'),JSON.stringify({operators:[operator]}));await writeFile(join(directory,'coverage/capital-geography.json'),JSON.stringify({cities:[target]}));
 const state=join(directory,'coverage/cursors/kirovohrad.json'),original='{"streetIndex":4}';await writeFile(state,original);let now=at;
 process.chdir(directory);process.env.COVERAGE_OPERATORS=operator.id;process.env.COVERAGE_COLLECTION_MODE='capital';delete process.env.DYNAMIC_COVERAGE_KEY_FILE;
 try{
  await assert.rejects(refresh({clock:()=>now,runner:async(_binary,args)=>{await writeFile(args[args.indexOf('--output')+1],JSON.stringify(packet()));await writeFile(args[args.indexOf('--state')+1],'{"streetIndex":5}');now=at+10;throw killed();}}),/Signing secret unavailable/);
  assert.equal(await readFile(state,'utf8'),original);assert(await absent('dynamic-coverage/manifest.json'));assert(await absent('dynamic-coverage/v2/manifest.json'));
  const report=JSON.parse(await readFile('coverage/refresh-report.json'));assert.equal(report.collections[0].status,'collected_checkpoint');assert.equal(report.errors[0].error,'collector_timeout');assert.equal(report.errors[0].checkpointRecovered,true);assert.equal(report.signing,'missing_key');
 }finally{process.chdir(previousCwd);for(const name of names){if(environment[name]===undefined)delete process.env[name];else process.env[name]=environment[name];}}
}));
