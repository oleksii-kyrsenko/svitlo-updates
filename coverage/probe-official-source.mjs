// Read-only evidence: existing collectors, isolated cursors, no signing or publication.
import {readFile,writeFile,mkdir,appendFile} from 'node:fs/promises';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {resolve,join,dirname,isAbsolute} from 'node:path';
import {pathToFileURL} from 'node:url';
import {collectorCommand} from './collector-registry.mjs';
import {validateBundle} from './build.mjs';
const execute=promisify(execFile),pdfScripts=new Set(['collect-cherkasy-documents.py','collect-vinnytsia-documents.py','collect-western-official.py','collect-rivne-zap.py']);

export function probePlan({operatorId,requestLimit='20',operators,cities,directory}){
 if(typeof operatorId!=='string'||!/^[-a-z0-9]+$/.test(operatorId)||!operators.some(o=>o.id===operatorId))throw Error('unknown_registry_operator');
 if(!/^(?:[1-9]|[1-9][0-9]|100)$/.test(String(requestLimit)))throw Error('invalid_request_limit_1_to_100');
 const operator=operators.find(o=>o.id===operatorId),targets=cities.filter(c=>operator.regionIds.includes(c.regionId));
 if(targets.length!==1||!targets[0].settlement||!targets[0].community)throw Error('unique_sourced_capital_required');
 const target=targets[0],limit=Number(requestLimit),command=collectorCommand(operatorId,{targetCity:target.settlement,fullCity:true,requestLimit:limit,budget:limit,streetBudget:limit});
 if(!command.targetCity||!command.args.includes('--request-limit'))throw Error('collector_has_no_bounded_capital_mode');
 const root=resolve(directory),output=join(root,'work','candidates.json'),cursor=join(root,'work','cursor.json'),args=[...command.args];
 for(const [flag,file] of [['--output',output],['--state',cursor]]){const i=args.indexOf(flag);if(i<0)throw Error('collector_has_no_isolated_output_or_cursor');args[i+1]=file;}
 return {operatorId,target,requestLimit:limit,output,cursor,args,artifact:join(root,'artifact'),needsPdf:pdfScripts.has(args[0].split('/').at(-1))};
}
const safeUrl=value=>{try{const u=new URL(value);return u.protocol==='https:'&&!u.username&&!u.password?u.origin+u.pathname:undefined;}catch{return undefined;}};
const houseKey=(r,h)=>JSON.stringify([r.regionId,r.settlement,r.community,r.street,h]);
const observedFields=new Set(['regionId','settlement','community','street','house','providerStreetId','officialCityId','checkedAt','expiresAt']);

export async function runProbe(plan,{runner=execute,clock=Date.now}={}){
 // Refuse an existing run directory rather than accidentally upload stale facts.
 await mkdir(dirname(dirname(plan.output)),{recursive:true});await mkdir(dirname(plan.output));await mkdir(plan.artifact);
 const startedAt=clock();let failure=null,packet=null,sidecar={},invalidPacket=false;
 try{await runner('python3',plan.args,{timeout:540000,maxBuffer:1024*1024,env:{...process.env,SVITLO_GEOGRAPHY_CACHE:join(dirname(plan.output),'geography-cache.json')}});}catch(error){failure=error.killed?'collector_timeout':'collector_failed';}
 try{sidecar=JSON.parse(await readFile(plan.output+'.report.json'));}catch{}
 try{
  const raw=await readFile(plan.output);if(raw.length>64*1024*1024)throw Error('oversize_candidate');packet=JSON.parse(raw);
  if(packet.schemaVersion!==1||packet.operatorId!==plan.operatorId||!Number.isFinite(packet.generatedAt)||packet.generatedAt<startedAt||packet.generatedAt>clock())throw Error('stale_or_wrong_operator_candidate');
  if(packet.records?.length)validateBundle(packet,clock());
  else if(!Array.isArray(packet.records)||!Array.isArray(packet.observedHouses))throw Error('invalid_empty_candidate');
  for(const r of [...packet.records,...packet.observedHouses||[]])if(r.regionId!==plan.target.regionId||r.settlement!==plan.target.settlement||r.community!==plan.target.community)throw Error('candidate_crosses_capital');
  packet={schemaVersion:1,operatorId:packet.operatorId,generatedAt:packet.generatedAt,expiresAt:packet.expiresAt,records:packet.records,observedHouses:(packet.observedHouses||[]).map(r=>Object.fromEntries(Object.entries(r).filter(([k])=>observedFields.has(k))))};
  await writeFile(join(plan.artifact,'candidates.json'),JSON.stringify(packet)+'\n');
 }catch(error){if(error.code!=='ENOENT')invalidPacket=true;packet=null;}
 const trace=Array.isArray(sidecar.requests)?sidecar.requests:[],requests=trace.map(r=>Object.fromEntries(Object.entries({sourceUrl:safeUrl(r.url),path:typeof r.path==='string'?r.path.split('?')[0]:undefined,httpStatus:r.httpStatus??r.status,checkedAt:r.checkedAt,bytes:r.bytes,sha256:r.sha256??r.responseSha256,error:typeof r.error==='string'&&/^[A-Za-z_]+$/.test(r.error)?r.error:undefined}).filter(([,v])=>v!==undefined)));
 const records=packet?.records||[],observed=packet?.observedHouses||[],positive=new Set(records.flatMap(r=>(r.houses||[]).map(h=>houseKey(r,h)))),unassigned=observed.filter(r=>!positive.has(houseKey(r,r.house)));
 const clocks=records.map(r=>r.checkedAt),statuses={};for(const r of requests)if(r.httpStatus)statuses[r.httpStatus]=(statuses[r.httpStatus]||0)+1;
 const traced=Array.isArray(sidecar.requests),exceeded=requests.length>plan.requestLimit,summary={schemaVersion:1,method:'read-only bounded existing public collector; not Android coverage',coverageMeasured:false,codeCommit:process.env.GITHUB_SHA||null,operatorId:plan.operatorId,target:plan.target,requestedLimit:plan.requestLimit,startedAt,finishedAt:clock(),requestCount:traced?requests.length:null,requestBoundVerified:traced&&!exceeded,httpStatuses:statuses,collectorFailure:failure,invalidPacket,records:records.length,positiveHouseFacts:positive.size,observedHouses:observed.length,unassignedObservedHouses:unassigned.length,sourceCheckedAtMin:clocks.length?Math.min(...clocks):null,sourceCheckedAtMax:clocks.length?Math.max(...clocks):null,sourceExpiresAt:packet?.expiresAt??null,status:exceeded?'request_bound_exceeded':!traced?'missing_request_trace':invalidPacket?'invalid_candidate':records.length?(failure?'partial_candidates_retained':'official_candidates_retained'):'source_unresolved',requests};
 await writeFile(join(plan.artifact,'unassigned-observations.json'),JSON.stringify(unassigned)+'\n');await writeFile(join(plan.artifact,'summary.json'),JSON.stringify(summary,null,2)+'\n');
 if(exceeded)throw Error('collector_exceeded_request_limit');return summary;
}
async function main(){
 const root=process.env.RUNNER_TEMP;if(!root||!isAbsolute(root))throw Error('runner_temp_required');
 const {operators}=JSON.parse(await readFile('coverage/sources.json')),{cities}=JSON.parse(await readFile('coverage/capital-geography.json'));
 const plan=probePlan({operatorId:process.env.SOURCE_OPERATOR,requestLimit:process.env.SOURCE_REQUEST_LIMIT||'20',operators,cities,directory:join(root,'official-source-probe')});
 if(process.argv.includes('--plan')){if(process.env.GITHUB_OUTPUT)await appendFile(process.env.GITHUB_OUTPUT,'needs_pdf='+String(plan.needsPdf)+'\n');console.log(JSON.stringify({operatorId:plan.operatorId,targetCity:plan.target.settlement,requestLimit:plan.requestLimit,needsPdf:plan.needsPdf}));return;}
 const r=await runProbe(plan);console.log(JSON.stringify({operatorId:r.operatorId,status:r.status,requests:r.requestCount,requestBoundVerified:r.requestBoundVerified,httpStatuses:r.httpStatuses,records:r.records}));if(!r.requestBoundVerified||r.invalidPacket)process.exitCode=2;
}
if(import.meta.url===pathToFileURL(process.argv[1]||'').href)await main();
