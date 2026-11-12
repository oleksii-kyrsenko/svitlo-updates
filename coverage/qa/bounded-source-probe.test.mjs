import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,readFile,writeFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {probePlan,runProbe} from '../probe-official-source.mjs';
const operators=JSON.parse(await readFile(new URL('../sources.json',import.meta.url))).operators;
const cities=JSON.parse(await readFile(new URL('../capital-geography.json',import.meta.url))).cities;
const plan=(directory,requestLimit='20',operatorId='volyn')=>probePlan({operatorId,requestLimit,operators,cities,directory});
test('registry and sourced capital select a bounded existing collector and separate output/cursor',()=>{
 const p=plan('/tmp/public-probe');assert.equal(p.target.regionId,'UA-07');assert.equal(p.target.settlement,cities.find(c=>c.regionId==='UA-07').settlement);assert.equal(p.args[0],'coverage/collect-city-forms.py');assert.equal(p.args[p.args.indexOf('--request-limit')+1],'20');assert.equal(p.output,'/tmp/public-probe/work/candidates.json');assert.equal(p.cursor,'/tmp/public-probe/work/cursor.json');assert.equal(p.needsPdf,false);assert.equal(plan('/tmp/public-probe','4','rivne').needsPdf,true);
});
test('untrusted IDs and limits fail without constructing an executable shell command',()=>{
 for(const id of ['missing','volyn;touch /tmp/injected','$(id)','../volyn','volyn\nother'])assert.throws(()=>plan('/tmp/public-probe','20',id),/registry/);
 for(const limit of ['0','101','-1','20.0','1e2',' 20','20;id','20\n',null])assert.throws(()=>plan('/tmp/public-probe',limit),/request_limit/);
 assert.equal(plan('/tmp/public-probe','100').requestLimit,100);assert.throws(()=>plan('/tmp/public-probe','20','zaporizhzhia'),/bounded_capital/);
});
async function temporary(run){const directory=await mkdtemp(join(tmpdir(),'source-probe-test-'));try{return await run(directory);}finally{await rm(directory,{recursive:true,force:true});}}
test('public source clocks and unassigned houses survive; request tokens are not artifacts',()=>temporary(async directory=>{
 const p=plan(directory,'2'),at=Date.UTC(2026,10,11,18),geo={regionId:p.target.regionId,settlement:p.target.settlement,community:p.target.community};
 const row={id:'source-house',official:true,...geo,street:'Навчальна',houses:['1'],scope:'house',queue:'2.1',sourceUrl:'https://energy.volyn.ua/public/',quote:'Навчальна,1:2.1',checkedAt:at+1,expiresAt:at+86400001};
 const packet={schemaVersion:1,operatorId:p.operatorId,generatedAt:at+3,expiresAt:row.expiresAt,records:[row],observedHouses:[{...geo,street:row.street,house:'1',checkedAt:at+1,expiresAt:row.expiresAt},{...geo,street:row.street,house:'2',checkedAt:at+1,expiresAt:row.expiresAt}]};let ticks=0;
 const r=await runProbe(p,{clock:()=>ticks++?at+10:at,runner:async(executable,args,options)=>{
  assert.equal(executable,'python3');assert.equal(options.shell,undefined);assert.deepEqual(args,p.args);assert.equal(options.env.SVITLO_GEOGRAPHY_CACHE,join(directory,'work','geography-cache.json'));
  await writeFile(p.output,JSON.stringify({...packet,transientToken:'private'}));await writeFile(p.output+'.report.json',JSON.stringify({requests:[{url:'https://energy.volyn.ua/public/?token=private',httpStatus:200,checkedAt:at+1,bytes:10,sha256:'a'.repeat(64),cookie:'private'}]}));
 }});
 assert.equal(r.sourceCheckedAtMin,row.checkedAt);assert.equal(r.positiveHouseFacts,1);assert.equal(r.unassignedObservedHouses,1);assert.equal(r.requestCount,1);assert.equal(r.requestBoundVerified,true);assert.deepEqual(JSON.parse(await readFile(join(p.artifact,'candidates.json'))),packet);assert.equal(JSON.parse(await readFile(join(p.artifact,'unassigned-observations.json')))[0].house,'2');assert(!JSON.stringify(r).includes('private'));assert.equal(r.requests[0].sourceUrl,'https://energy.volyn.ua/public/');
}));
test('the actual protected source response remains unresolved, with no invented candidate or clock',()=>temporary(async directory=>{
 const p=plan(directory);const r=await runProbe(p,{runner:async()=>{await writeFile(p.output+'.report.json',JSON.stringify({requests:[{path:'/public/',httpStatus:403,error:'HTTPError'}]}));throw Error('do not retain body or token');}});
 assert.equal(r.status,'source_unresolved');assert.equal(r.collectorFailure,'collector_failed');assert.equal(r.records,0);assert.deepEqual(r.httpStatuses,{'403':1});assert.equal(r.sourceCheckedAtMin,null);
}));
test('cross-capital candidates are quarantined from public artifacts',()=>temporary(async directory=>{
 const p=plan(directory),at=Date.now();let ticks=0;const r=await runProbe(p,{clock:()=>ticks++?at+10:at,runner:async()=>{await writeFile(p.output,JSON.stringify({schemaVersion:1,operatorId:'volyn',generatedAt:at+1,records:[],observedHouses:[{regionId:'UA-05',settlement:'Інше',community:'Інша'}]}));await writeFile(p.output+'.report.json','{"requests":[]}');}});
 assert.equal(r.invalidPacket,true);assert.equal(r.status,'invalid_candidate');await assert.rejects(readFile(join(p.artifact,'candidates.json')),/ENOENT/);
}));
test('an existing run directory is never reused for stale candidate evidence',()=>temporary(async directory=>{
 const p=plan(directory);await runProbe(p,{runner:async()=>{}});let executed=false;await assert.rejects(runProbe(p,{runner:async()=>{executed=true;}}),/EEXIST/);assert.equal(executed,false);
}));
test('a reported request bound violation fails and retains the violation evidence',()=>temporary(async directory=>{
 const p=plan(directory,'1');await assert.rejects(runProbe(p,{runner:async()=>{await writeFile(p.output+'.report.json',JSON.stringify({requests:[{httpStatus:200},{httpStatus:200}]}));}}),/exceeded_request_limit/);const r=JSON.parse(await readFile(join(p.artifact,'summary.json')));assert.equal(r.requestCount,2);assert.equal(r.status,'request_bound_exceeded');
}));
test('missing report or request trace cannot prove a successful bounded source probe',()=>temporary(async directory=>{
 for(const [name,sidecar] of [['absent',null],['untraced',{records:0}]]){
  const p=plan(join(directory,name)),r=await runProbe(p,{runner:async()=>{if(sidecar)await writeFile(p.output+'.report.json',JSON.stringify(sidecar));}});assert.equal(r.requestCount,null);assert.equal(r.requestBoundVerified,false);assert.equal(r.status,'missing_request_trace');
 }
}));
