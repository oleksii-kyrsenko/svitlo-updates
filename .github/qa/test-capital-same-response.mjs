import test from 'node:test';import assert from 'node:assert/strict';
import {createPrivacySanitizer,createAnonymousSessionFetcher,createRecorder,createReplay,requestIdentity,addressFingerprint,originalPlace,regressionResult,canonical,digest} from './capital-same-response.mjs';
const raw=x=>Buffer.from(JSON.stringify(x));
test('ASD subscriber fields are not retained while exact address queue and population survive',()=>{
 const p=createPrivacySanitizer(),input={'hydra:totalItems':2,'hydra:member':[{id:123,buildingName:'1-А',chergGpv:'12',eic:'56XPRIVATE',accountNumber:'12345',subscriberName:'Private person',city:{id:7,name:'Місто',subscriberName:'Private'}}]};
 const s=p.response('https://power-api.loe.lviv.ua/api/pw_accounts?city.id=7',raw(input),'application/json'),text=s.bytes.toString(),value=JSON.parse(text);
 for(const secret of ['12345','56XPRIVATE','Private','subscriber','account','"id":123'])assert(!text.includes(secret));
 assert.equal(value['hydra:totalItems'],2);assert.equal(value['hydra:member'][0].buildingName,'1-А');assert.equal(value['hydra:member'][0].chergGpv,'12');
});
test('Cherkasy private account references are pseudonymized and only remapped in memory for a real request',()=>{
 const p=createPrivacySanitizer(),privateId='991122334455',list=JSON.parse(p.response('https://cabinet.cherkasyoblenergo.com/api_new/disconn.php?op=ls_list_by_addr',raw({[privateId]:{LS:privateId,NAME:'Private person'}}),'application/json').bytes);
 assert.deepEqual(list,[{LS:'qa-account-1'}]);
 const request={url:'https://cabinet.cherkasyoblenergo.com/api_new/disconn.php?op=disconn_by_ls&abon_ls='+list[0].LS,body:''};
 assert(p.networkRequest(request).url.includes(privateId));assert(!JSON.stringify(request).includes(privateId));
 const answer=p.response(request.url,raw({ACCOUNT:privateId,DISCONN_QUEUQ:[{QUEUE_INFO:'ГПВ: 2.1',LS:privateId}]}),'application/json').bytes.toString();
 assert(!answer.includes(privateId));assert(!answer.includes('ACCOUNT'));assert(answer.includes('2.1'));
});
test('freeform replies retain only queue confirmation fields, not customer data or forecasts',()=>{
 const p=createPrivacySanitizer(),result=JSON.parse(p.response('https://be-svitlo.oe.if.ua/schedule-by-search',raw({current:{queue:2,subQueue:1,hasQueue:'yes',name:'Private',accountNumber:'123'},schedule:[{account:'private'}]}),'application/json').bytes);
 assert.deepEqual(result,{current:{hasQueue:'yes',queue:2,subQueue:1}});
});
test('signed public package bytes remain exact for verification',()=>{
 const p=createPrivacySanitizer(),bytes=raw({payload:'exact==',signature:'signature==',account:'public-signed-field'});
 assert.deepEqual(p.response('https://raw.githubusercontent.com/owner/repo/main/manifest.json',bytes,'application/json').bytes,bytes);
});
test('replay refuses any new source request instead of falling through to live network',async()=>{
 const r=createReplay({schemaVersion:1,kind:'sanitized-public-source-response-snapshot',entries:[]});
 await assert.rejects(r.fetcher('https://example.org/source'),{code:'fixture_miss'});assert.equal(r.misses.length,1);
});
test('volatile request time is normalized but authentication and semantic request headers are not ignored',()=>{
 const a=requestIdentity('https://kiroe.com.ua/electricity-blackout/city/7?t=1',{headers:{'X-Requested-With':'XMLHttpRequest'}}),b=requestIdentity('https://kiroe.com.ua/electricity-blackout/city/7?t=2',{headers:{'X-Requested-With':'XMLHttpRequest'}});
 assert.deepEqual(a,b);assert.throws(()=>requestIdentity('https://example.org',{headers:{Cookie:'private'}}),/authenticated/);
 assert.notDeepEqual(a,requestIdentity(a.url,{headers:{Accept:'text/html'}}));
});
test('original UI selectors can be reused but all queue data is removed',()=>{
 const c={id:'case',regionId:'UA-30',city:'Місто',exactStreet:'вулиця Нова',exactHouse:'1',osmType:'way',osmId:1,latitude:50.1,longitude:30.2,baseline:{operatorId:'example'}};
 const place=originalPlace(c,{persistedPlace:{regionId:c.regionId,operatorId:'example',addressParts:{settlement:c.city,street:c.exactStreet,house:'1'},officialCityId:'city:street',queue:'2.1',queueOrigin:'manual',reminders:true}});
 assert.equal(place.officialCityId,'city:street');assert(!('queue' in place));assert(!('queueOrigin' in place));assert(!('reminders' in place));
 assert.equal(addressFingerprint(c),digest(canonical({regionId:c.regionId,city:c.city,osmType:'way',osmId:1,latitude:50.1,longitude:30.2,exactStreet:c.exactStreet,exactHouse:'1'})));
 assert.equal(regressionResult(c,{status:'ready',queue:'2.1',origin:'public'},'a'.repeat(40),'b'.repeat(64)).provenance,'public');
});

test('anonymous public HTTP sessions use memory-only source cookies and normal page referer',async()=>{
 const calls=[],fetcher=async(url,options)=>{calls.push({url,headers:new Headers(options.headers)});return new Response('public page',{headers:{'Set-Cookie':'public-session=opaque-private-cookie; Path=/; Secure'}});};
 const session=createAnonymousSessionFetcher({fetcher,clock:()=>1000});
 await session('https://www.dtek-oem.com.ua/ua/shutdowns',{credentials:'include'});
 await session('https://www.dtek-oem.com.ua/ua/ajax',{method:'POST',credentials:'include'});
 assert.equal(calls[1].headers.get('cookie'),'public-session=opaque-private-cookie');assert.equal(calls[1].headers.get('referer'),'https://www.dtek-oem.com.ua/ua/shutdowns');
 await session('https://www.dtek-oem.com.ua/ua/ajax',{method:'POST',credentials:'omit'});assert.equal(calls[2].headers.get('cookie'),null);
 await session('https://example.org/ua/ajax',{method:'POST'});assert.equal(calls[3].headers.get('cookie'),null);assert.equal(calls[3].headers.get('referer'),null);
 const recorder=createRecorder({fetcher:session});await recorder.fetcher('https://www.dtek-oem.com.ua/ua/ajax',{method:'POST',credentials:'include'});
 assert(!JSON.stringify(recorder.snapshot()).includes('opaque-private-cookie'));
});
test('expired, foreign-domain and different-path session cookies are never forwarded',async()=>{
 const calls=[],session=createAnonymousSessionFetcher({clock:()=>1000,fetcher:async(url,options)=>{calls.push(new Headers(options.headers));const headers=new Headers();headers.append('Set-Cookie','gone=private-expired; Max-Age=0; Path=/');headers.append('Set-Cookie','foreign=private-foreign; Domain=example.org; Path=/');headers.append('Set-Cookie','scoped=private-scoped; Path=/separate/');return new Response('public',{headers});}});
 await session('https://kiroe.com.ua/electricity-blackout');await session('https://kiroe.com.ua/electricity-blackout/city/7',{method:'POST'});
 assert.equal(calls[1].get('cookie'),null);assert.equal(calls[1].get('referer'),'https://kiroe.com.ua/electricity-blackout');
 await assert.rejects(session('https://kiroe.com.ua',{headers:{Cookie:'provided-authentication'}}),/authenticated_requests_forbidden/);
});
