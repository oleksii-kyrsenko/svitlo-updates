import {validateBundle} from './build.mjs';
import {canonicalStreet,canonicalHouse} from './snapshots.mjs';
const LIMIT=8*1024*1024;
const bytes=b=>Buffer.byteLength(JSON.stringify(b)+'\n');
const house=canonicalHouse;
const geo=r=>JSON.stringify([r.regionId,r.settlement,r.community]);
const street=r=>JSON.stringify([geo(r),canonicalStreet(r.street)]);
const selector=r=>r.officialCityId||canonicalStreet(r.street)||'';
function retainedLegacy(old,current,now){
 if(!old||old.expiresAt<=now)return null;
 const byStreet=new Map(),settlements=new Map();
 for(const r of current.records){
  const key=street(r);if(!byStreet.has(key))byStreet.set(key,[]);byStreet.get(key).push(r);
  if(r.scope==='settlement'){const g=geo(r);if(!settlements.has(g))settlements.set(g,[]);settlements.get(g).push(r);}
 }
 const records=[];
 for(const r of old.records){
  if(r.expiresAt<=now)continue;
  const candidates=[...(byStreet.get(street(r))||[]),...(settlements.get(geo(r))||[])];
  if(r.scope==='house'){
   const houses=r.houses.filter(h=>{
    if(candidates.some(c=>(c.excludedHouses||[]).some(x=>house(x)===house(h))))return false;
    const matches=candidates.filter(c=>c.scope!=='house'||c.houses.some(x=>house(x)===house(h)));
    if(!matches.length||new Set(matches.map(c=>c.queue)).size!==1||matches[0].queue!==r.queue)return false;
    const identities=new Set(matches.filter(c=>c.scope!=='settlement').map(selector));
    return identities.size<=1&&matches.some(c=>c.scope==='house'&&selector(c)===selector(r));
   });
   if(houses.length)records.push({...r,houses});
  }else{
   const relevant=r.scope==='settlement'?current.records.filter(c=>geo(c)===geo(r)):candidates;
   if(relevant.some(c=>c.queue!==r.queue))continue;
   if(relevant.some(c=>c.scope===r.scope&&selector(c)===selector(r)&&c.queue===r.queue))records.push(r);
  }
 }
 if(!records.length)return null;
 // Generation and observation deadlines are deliberately unchanged.
 const retained={...old,records};validateBundle(retained,now);return bytes(retained)<=LIMIT?retained:null;
}
export function legacyCompatibleBundles(current,previous,now=Date.now()){
 const bundles=[],constraints=[];
 for(const b of current){
  validateBundle(b,now);const size=bytes(b);
  if(size<=LIMIT){bundles.push(b);continue;}
  const retained=retainedLegacy(previous.find(old=>old.operatorId===b.operatorId),b,now);
  if(retained)bundles.push(retained);
  constraints.push({operatorId:b.operatorId,reason:'operator_exceeds_legacy_bundle_limit',bytes:size,previousUnexpiredRetained:Boolean(retained),legacyRecords:retained?.records.length||0,fullRecords:b.records.length});
 }
 return {bundles,constraints};
}
