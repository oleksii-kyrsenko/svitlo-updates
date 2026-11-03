// Generic external regression harness. Application source remains in private roots.
import {readFile,writeFile,mkdir,symlink,access} from 'node:fs/promises';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {resolve,dirname,join} from 'node:path';
import {pathToFileURL} from 'node:url';

export const ORIGINAL_RUNTIME='243a9a339b1fdcfa44f3850aee2e051e121b0dff';
const MAX_RESPONSE=12*1024*1024,MAX_CASE=32*1024*1024;
export const digest=value=>createHash('sha256').update(value).digest('hex');
export function canonical(value){
 if(value===null||typeof value!=='object')return JSON.stringify(value);
 if(Array.isArray(value))return '['+value.map(canonical).join(',')+']';
 return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonical(value[k])).join(',')+'}';
}
export function addressFingerprint(c){
 const keys=['regionId','city','osmType','osmId','latitude','longitude','exactStreet','exactHouse'];
 if(keys.some(k=>c[k]===undefined||c[k]===null||c[k]===''))throw Error('incomplete_frozen_address');
 return digest(canonical(Object.fromEntries(keys.map(k=>[k,c[k]]))));
}
function safeURL(value){const u=new URL(String(value));if(u.protocol!=='https:'||u.username||u.password)throw Error('public_https_required');return u;}
export function requestIdentity(url,options={}){
 const u=safeURL(url);
 if(u.hostname==='kiroe.com.ua')u.searchParams.delete('t');
 if(u.hostname==='raw.githubusercontent.com'&&u.pathname.endsWith('/manifest.json'))u.searchParams.delete('v');
 u.searchParams.sort();
 const method=(options.method||'GET').toUpperCase();
 const headers=Object.fromEntries(new Headers(options.headers||{}));
 if(headers.authorization||headers.cookie)throw Error('authenticated_requests_forbidden');
 const body=options.body==null?'':String(options.body);
 return {method,url:u.href,body,headers:Object.fromEntries(Object.entries(headers).filter(([k])=>['accept','content-type','accept-language','user-agent','x-requested-with'].includes(k)))};
}
const requestKey=r=>canonical({method:r.method,url:r.url,body:r.body,headers:r.headers});
const safeError=e=>({name:typeof e?.name==='string'?e.name:'Error',code:typeof e?.code==='string'?e.code.slice(0,60):'source_request_failed'});
function opaqueError(value){return Object.assign(Error('Recorded source request failed'),value);}
export function createPrivacySanitizer(){
 const forward=new Map(),reverse=new Map();let next=0;
 function pseudonym(value){const original=String(value);if(!forward.has(original)){const token='qa-account-'+(++next);forward.set(original,token);reverse.set(token,original);}return forward.get(original);}
 function generic(value){
  if(Array.isArray(value))return value.map(generic);
  if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).filter(([k])=>!/^(?:eic|account(?:number|id)?|subscriber(?:id|name)?|abon.*|personal.*|phone|email|ls|login|password)$/i.test(k)).map(([k,v])=>[k,generic(v)]));
  return value;
 }
 function cleanJSON(url,value){
  const u=new URL(url),op=u.searchParams.get('op');
  if(u.hostname==='cabinet.cherkasyoblenergo.com'){
   if(op==='ls_list_by_addr')return Object.values(value||{}).map(r=>({LS:pseudonym(r.LS)}));
   if(op==='disconn_by_ls')return {DISCONN_QUEUQ:Object.values(value?.DISCONN_QUEUQ||{}).map(r=>({QUEUE_INFO:String(r.QUEUE_INFO||'')}))};
  }
  if(u.pathname.endsWith('/pw_accounts')){
   const cleanRow=r=>({buildingName:r.buildingName,chergGpv:r.chergGpv,...(r.city?{city:{id:r.city.id,name:r.city.name}}:{})});
   if(Array.isArray(value))return value.map(cleanRow);
   return {...Object.fromEntries(Object.entries(value||{}).filter(([k])=>!['hydra:member','member'].includes(k)).map(([k,v])=>[k,generic(v)])),...(Array.isArray(value?.['hydra:member'])?{'hydra:member':value['hydra:member'].map(cleanRow)}:{}),...(Array.isArray(value?.member)?{member:value.member.map(cleanRow)}:{})};
  }
  if(u.hostname==='kiroe.com.ua'&&/\/house\//.test(u.pathname))return Object.fromEntries(Object.entries(value||{}).map(([k,v])=>[k,k==='data'&&Array.isArray(v)?v.map(r=>({HouseName:r.HouseName,chergGpv:r.chergGpv,CityId:r.CityId,StreetId:r.StreetId})):generic(v)]));
  if(u.hostname==='be-svitlo.oe.if.ua'&&u.pathname.endsWith('/schedule-by-search'))return {current:value?.current?{hasQueue:value.current.hasQueue,queue:value.current.queue,subQueue:value.current.subQueue}:value?.current};
  return generic(value);
 }
 return {
  response(url,raw,contentType){
   // These are already public, signed, normalized datasets. Exact bytes are
   // essential to signature verification and must not be transformed.
   if(new URL(url).hostname==='raw.githubusercontent.com')return {bytes:raw,contentType};
   let value;try{value=JSON.parse(new TextDecoder().decode(raw));}catch{return {bytes:raw,contentType};}
   return {bytes:Buffer.from(JSON.stringify(cleanJSON(url,value))),contentType:'application/json;charset=utf-8'};
  },
  networkRequest(request){
   const u=new URL(request.url),params=new URLSearchParams(request.body);
   for(const key of ['abon_ls','accountNumber']){
    if(u.searchParams.has(key)){const original=reverse.get(u.searchParams.get(key));if(!original)throw Error('unrecognized_account_pseudonym');u.searchParams.set(key,original);}
    if(params.has(key)&&params.get(key)){const original=reverse.get(params.get(key));if(!original)throw Error('unrecognized_account_pseudonym');params.set(key,original);}
   }
   return {url:u.href,body:request.body?params.toString():''};
  }
 };
}
// Match the anonymous HTTP session behavior of the app's public WebView
// transport. This is not Chromium/JavaScript execution or an authenticated
// session. Cookie values are used only in memory and never reach a fixture.
export function createAnonymousSessionFetcher({fetcher=fetch,clock=Date.now}={}){
 const cookies=new Map(),pages=new Map();
 const supported=u=>u.hostname==='kiroe.com.ua'||/^www\.dtek-(?:dnem|oem|kem|krem|dem|pem|vvm)\.com\.ua$/.test(u.hostname);
 return async(url,options={})=>{
  const u=safeURL(url),headers=new Headers(options.headers||{}),method=(options.method||'GET').toUpperCase();
  const allowed=supported(u)&&options.credentials!=='omit';
  if(headers.has('authorization')||headers.has('cookie'))throw Error('authenticated_requests_forbidden');
  if(allowed){
   const values=[...(cookies.get(u.origin)||new Map()).values()].filter(c=>c.expiresAt>clock()&&u.pathname.startsWith(c.path));
   if(values.length)headers.set('Cookie',values.map(c=>c.pair).join('; '));
   if(method!=='GET'&&pages.has(u.origin)){headers.set('Referer',pages.get(u.origin));headers.set('Origin',u.origin);}
  }
  const answer=await fetcher(u.href,{...options,headers});
  if(allowed){
   const target=answer.url?new URL(answer.url):u;
   if(target.origin===u.origin){
    const jar=cookies.get(u.origin)||new Map();
    for(const line of answer.headers.getSetCookie?.()||[]){
     const parts=line.split(';').map(v=>v.trim()),pair=parts.shift(),at=pair.indexOf('=');if(at<1)continue;
     const attributes=Object.fromEntries(parts.map(v=>{const i=v.indexOf('=');return [v.slice(0,i<0?undefined:i).toLowerCase(),i<0?'':v.slice(i+1)];}));
     if(attributes.domain&&attributes.domain.replace(/^\./,'').toLowerCase()!==u.hostname)continue;
     const path=attributes.path?.startsWith('/')?attributes.path:u.pathname.slice(0,u.pathname.lastIndexOf('/')+1)||'/';
     const age=attributes['max-age'],expiry=age!==undefined&&Number.isFinite(Number(age))?clock()+Number(age)*1000:attributes.expires?Date.parse(attributes.expires):Infinity;
     jar.set(pair.slice(0,at)+'|'+path,{pair,path,expiresAt:Number.isNaN(expiry)?Infinity:expiry});
    }
    cookies.set(u.origin,jar);
    if(method==='GET'&&answer.ok&&!u.search&&['/ua/shutdowns','/ua/shutdowns-schedule','/electricity-blackout'].includes(u.pathname))pages.set(u.origin,u.href);
   }
  }
  return answer;
 };
}
const hostQueues=new Map();
async function throttle(url){
 const host=new URL(url).hostname,previous=hostQueues.get(host)||Promise.resolve();
 const turn=previous.catch(()=>{}).then(()=>new Promise(r=>setTimeout(r,1050)));hostQueues.set(host,turn);await turn;
}
function response(entry){if(entry.error)throw opaqueError(entry.error);return new Response([204,205,304].includes(entry.status)?null:Buffer.from(entry.bodyBase64,'base64'),{status:entry.status,headers:entry.headers});}
export function createRecorder({fetcher=fetch,clock=Date.now,maxRequests=120}={}){
 const entries=new Map(),pending=new Map(),privacy=createPrivacySanitizer();let total=0;
 const wrapped=async(url,options={})=>{
  const request=requestIdentity(url,options),key=requestKey(request);
  if(entries.has(key))return response(entries.get(key));
  if(pending.has(key)){await pending.get(key);return response(entries.get(key));}
  if(entries.size+pending.size>=maxRequests)throw Object.assign(Error('Bounded source recording request limit'),{code:'recording_limit'});
  const promise=(async()=>{
   const observedAt=clock();let entry={request,observedAt};
   try{
    const real=privacy.networkRequest({...request,url:safeURL(url).href});await throttle(request.url);
    if(options.signal?.aborted)throw Object.assign(Error('Aborted'),{name:'AbortError'});
    const source=await fetcher(real.url,{...options,method:request.method,headers:request.headers,body:request.method==='GET'||request.method==='HEAD'?undefined:real.body});
    const contentType=source.headers.get('content-type')||'application/octet-stream';
    if(Number(source.headers.get('content-length'))>MAX_RESPONSE)throw Error('source_response_size_limit');
    const raw=Buffer.from(await source.arrayBuffer());if(raw.length>MAX_RESPONSE)throw Error('source_response_size_limit');
    const safe=privacy.response(request.url,raw,contentType);total+=safe.bytes.length;if(total>MAX_CASE)throw Error('source_case_size_limit');
    entry={...entry,status:source.status,headers:{'content-type':safe.contentType},bodyBase64:safe.bytes.toString('base64')};
   }catch(error){entry={...entry,error:safeError(error)};}
   entries.set(key,entry);
  })();pending.set(key,promise);try{await promise;}finally{pending.delete(key);}return response(entries.get(key));
 };
 return {fetcher:wrapped,snapshot:()=>({schemaVersion:1,kind:'sanitized-public-source-response-snapshot',privacy:'Public address/queue fields only; ASD account IDs removed; Cherkasy account references pseudonymized in memory; no cookies or authentication headers.',entries:[...entries.values()].sort((a,b)=>requestKey(a.request).localeCompare(requestKey(b.request)))})};
}
export function createReplay(snapshot){
 if(snapshot?.schemaVersion!==1||snapshot.kind!=='sanitized-public-source-response-snapshot'||!Array.isArray(snapshot.entries))throw Error('invalid_source_snapshot');
 const entries=new Map(snapshot.entries.map(e=>[requestKey(e.request),e])),misses=[];
 return {misses,fetcher:async(url,options={})=>{
  const request=requestIdentity(url,options),entry=entries.get(requestKey(request));
  if(!entry){misses.push(request);throw Object.assign(Error('Replay has no matching source response; network is forbidden'),{code:'fixture_miss'});}
  return response(entry);
 }};
}
export async function prepareOldRuntime(repo,root,commit=ORIGINAL_RUNTIME){
 if(!/^[a-f0-9]{40}$/.test(commit))throw Error('invalid_original_commit');
 await mkdir(root,{recursive:true});
 const archive=execFileSync('git',['-C',repo,'archive','--format=tar',commit,'shared','apps/mobile/queue-lookup.js','apps/mobile/geocoding.js','package.json'],{maxBuffer:32*1024*1024});
 const file=join(root,'source.tar');await writeFile(file,archive);execFileSync('tar',['-xf',file,'-C',root]);
 try{await access(join(root,'node_modules'));}catch{await symlink(join(repo,'node_modules'),join(root,'node_modules'),'dir');}
 return root;
}
export async function verifyRuntimeTree(repo,root,commit){
 if(!/^[a-f0-9]{40}$/.test(commit))throw Error('invalid_runtime_commit');
 const paths=['shared','apps/mobile/queue-lookup.js','apps/mobile/geocoding.js','package.json'];
 const lines=execFileSync('git',['-C',repo,'ls-tree','-r','-z',commit,'--',...paths],{encoding:'utf8'}).split('\0').filter(Boolean);
 const verified=[];
 for(const line of lines){
  const match=line.match(/^[0-7]+ blob ([a-f0-9]{40})\t(.+)$/);if(!match)throw Error('unsupported_runtime_tree_entry');
  const bytes=await readFile(join(root,match[2])),blob=createHash('sha1').update('blob '+bytes.length+'\0').update(bytes).digest('hex');
  if(blob!==match[1])throw Error('runtime_source_differs_from_pinned_commit');verified.push({path:match[2],gitBlob:blob,sha256:digest(bytes)});
 }
 return {commit,verifiedFiles:verified.length,sourceTreeSha256:digest(canonical(verified))};
}
async function runtime(root,adaptive){
 const queue=await import(pathToFileURL(join(root,'apps/mobile/queue-lookup.js')).href);
 const dynamic=await import(pathToFileURL(join(root,adaptive?'shared/dynamic-coverage-v2.js':'shared/dynamic-coverage.js')).href);
 return {queue,create:adaptive?dynamic.createAdaptiveDynamicCoverage:dynamic.createDynamicCoverage};
}
function memory(){const values=new Map();return {getItem:async k=>values.get(k)||null,setItem:async(k,v)=>values.set(k,v)};}
async function invoke(runtime,place,fetcher,now,browserTransport=false){
 const dynamicCoverage=runtime.create({fetcher,storage:memory(),now:()=>now});
 const publicSourceCache=runtime.queue.createPublicSourceCache({fetcher,storage:memory(),now:()=>now});
 try{return await runtime.queue.lookupPlaceQueue(structuredClone(place),{fetcher,...(browserTransport?{browserFetcher:fetcher}:{}),dynamicCoverage,publicSourceCache,now});}
 catch(error){return {status:'regression-harness-error',error:safeError(error)};}
}
export function regressionResult(c,result,commit,snapshotSha256){
 return {caseId:c.id,addressFingerprint:addressFingerprint(c),runtimeCommit:commit,sourceSnapshotSha256:snapshotSha256,status:result.status,queue:result.queue||null,provenance:result.status==='ready'&&result.origin!=='public'?'official':result.origin||null,scope:result.scope||null,sourceUrl:result.sourceUrl||null,queueTransport:result.queueTransport||null};
}
export function originalPlace(c,audited){
 const source=audited?.persistedPlace||{regionId:c.regionId,operatorId:c.baseline.operatorId,address:[c.city,c.exactStreet,c.exactHouse].join(', '),addressParts:{settlement:c.city,street:c.exactStreet,house:c.exactHouse},addressContext:{regionId:c.regionId,community:c.community,settlement:c.city}};
 const allowed=['regionId','operatorId','operatorOrigin','operatorConfirmed','address','addressParts','addressContext','officialCityId','addressSelection','latitude','longitude'];
 const p=Object.fromEntries(allowed.filter(k=>source[k]!==undefined).map(k=>[k,source[k]]));
 if(p.operatorId!==c.baseline.operatorId||p.regionId!==c.regionId)throw Error('original_ui_operator_or_region_changed');
 const a=p.addressParts||{};
 if(a.settlement!==c.city||String(a.house).toLocaleLowerCase('uk')!==String(c.exactHouse).toLocaleLowerCase('uk'))throw Error('original_ui_settlement_or_house_changed');
 return p;
}
function options(argv){
 const result={};for(let i=0;i<argv.length;i++){const key=argv[i];if(['--record','--replay','--prepare-old','--resume','--anonymous-session'].includes(key))result[key.slice(2)]=true;else if(key.startsWith('--')&&argv[i+1]&&!argv[i+1].startsWith('--'))result[key.slice(2)]=argv[++i];else throw Error('invalid_cli_argument');}
 if(Boolean(result.record)===Boolean(result.replay))throw Error('Specify exactly one of --record or --replay');
 for(const name of ['old-root','candidate-root','baseline','out'])if(!result[name])throw Error('Missing --'+name);
 return result;
}
async function main(args){
 const baselineBytes=await readFile(args.baseline),baseline=JSON.parse(baselineBytes),oldCommit=baseline.originRuntimeCommit||ORIGINAL_RUNTIME;
 if(oldCommit!==ORIGINAL_RUNTIME)throw Error('original_runtime_differs_from_approved_baseline');
 const root=resolve(args['candidate-root']),oldRoot=resolve(args['old-root']),out=resolve(args.out);await mkdir(out,{recursive:true});
 const candidateCommit=args['candidate-commit']||execFileSync('git',['-C',root,'rev-parse','HEAD'],{encoding:'utf8'}).trim();if(!/^[a-f0-9]{40}$/.test(candidateCommit))throw Error('invalid_candidate_commit');
 if(args['prepare-old'])await prepareOldRuntime(root,oldRoot,oldCommit);
 const sourceTrees={original:await verifyRuntimeTree(root,oldRoot,oldCommit),candidate:await verifyRuntimeTree(root,root,candidateCommit)};
 const old=await runtime(oldRoot,false),candidate=await runtime(root,true);
 const originalSummary=args['original-summary']?JSON.parse(await readFile(args['original-summary'])):null;
 let cases=baseline.cases.filter(c=>c.baseline?.category==='official_house');if(cases.length!==38)throw Error('expected38originalsuccesses');
 if(args['case-ids'])cases=cases.filter(c=>args['case-ids'].split(',').includes(c.id));if(args.limit)cases=cases.slice(0,Number(args.limit));
 const results=[],references=[];const startedAt=new Date().toISOString();
 for(const c of cases){
  const folder=join(out,c.id);await mkdir(folder,{recursive:true});let audited=null,inputSource=null;
  const row=originalSummary?.results?.find(r=>r.id===c.id);
  if(row?.resultPath){try{const bytes=await readFile(row.resultPath);audited=JSON.parse(bytes);inputSource={sha256:digest(bytes),method:'original-audited-ui-address-selectors-queue-fields-removed'};}catch{}}
  const place=originalPlace(c,audited);let snapshot;
  let existing=false;try{await access(join(folder,'source-snapshot.json'));existing=true;}catch{}
  if(args.record&&existing&&!args.resume)throw Error('Existing immutable source snapshot; use --resume or a new output directory');
  if(args.record&&!(existing&&args.resume)){
   const at=Date.now(),record=createRecorder({fetcher:args['anonymous-session']?createAnonymousSessionFetcher():fetch});
   await invoke(old,place,record.fetcher,at,Boolean(args['anonymous-session']));await invoke(candidate,place,record.fetcher,at,Boolean(args['anonymous-session']));
   snapshot={...record.snapshot(),transport:{anonymousSession:Boolean(args['anonymous-session']),javascriptExecuted:false,cookieValuesPersisted:false},recordedAt:at,caseId:c.id,addressFingerprint:addressFingerprint(c),input:place,inputSource,baselineSha256:digest(baselineBytes)};
   await writeFile(join(folder,'source-snapshot.json'),JSON.stringify(snapshot)+'\n');
  }else snapshot=JSON.parse(await readFile(join(folder,'source-snapshot.json')));
  if(snapshot.caseId!==c.id||snapshot.addressFingerprint!==addressFingerprint(c)||snapshot.baselineSha256!==digest(baselineBytes))throw Error('snapshot_frozen_identity_changed');
  const bytes=await readFile(join(folder,'source-snapshot.json')),sha=digest(bytes),first=createReplay(snapshot),second=createReplay(snapshot);
  const before=regressionResult(c,await invoke(old,snapshot.input,first.fetcher,snapshot.recordedAt,snapshot.transport?.anonymousSession),oldCommit,sha);
  const after=regressionResult(c,await invoke(candidate,snapshot.input,second.fetcher,snapshot.recordedAt,snapshot.transport?.anonymousSession),candidateCommit,sha);
  const passed=before.status==='ready'&&after.status==='ready'&&before.provenance==='official'&&after.provenance==='official'&&before.queue===c.baseline.queue&&after.queue===c.baseline.queue&&!first.misses.length&&!second.misses.length;
  const category=passed?'preserved':first.misses.length||second.misses.length?'replay-incomplete':before.status!=='ready'?'original-source-blocked':before.queue!==c.baseline.queue?'original-source-queue-changed':'candidate-regression';
  const beforeBytes=Buffer.from(JSON.stringify(before,null,2)+'\n'),afterBytes=Buffer.from(JSON.stringify(after,null,2)+'\n');await writeFile(join(folder,'before.json'),beforeBytes);await writeFile(join(folder,'after.json'),afterBytes);
  const item={caseId:c.id,city:c.city,operatorId:c.baseline.operatorId,expectedQueue:c.baseline.queue,before:before.queue,beforeStatus:before.status,after:after.queue,afterStatus:after.status,passed,category,replayMisses:first.misses.length+second.misses.length,requests:snapshot.entries.length};results.push(item);
  references.push({caseId:c.id,addressFingerprint:addressFingerprint(c),sourceSnapshot:{path:c.id+'/source-snapshot.json',sha256:sha},before:{path:c.id+'/before.json',sha256:digest(beforeBytes)},after:{path:c.id+'/after.json',sha256:digest(afterBytes)}});
  const report={schemaVersion:1,kind:'same-response-original-success-regression',startedAt,completedAt:new Date().toISOString(),originRuntimeCommit:oldCommit,candidateRuntimeCommit:candidateCommit,sourceTrees,baselineSha256:digest(baselineBytes),requested:cases.length,preserved:results.filter(r=>r.passed).length,passed:results.length===38&&results.every(r=>r.passed),results,sameResponseRegressions:references,limitations:['This is a source-response integration regression, not an Android UI coverage audit.','Sanitized fixtures preserve public address/queue semantics; raw account identifiers are never persisted.','Blocked or naturally changed original sources cannot establish an unchanged historical successful result.']};
  await writeFile(join(out,'report.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(item));
 }
 const report=JSON.parse(await readFile(join(out,'report.json')));console.log(JSON.stringify({requested:report.requested,preserved:report.preserved,passed:report.passed}));return report.passed?0:2;
}
if(import.meta.url===pathToFileURL(process.argv[1]||'').href){try{process.exitCode=await main(options(process.argv.slice(2)));}catch(error){console.error(error?.message||'Regression harness failure');process.exitCode=1;}}
