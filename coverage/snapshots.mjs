import {createHash} from 'node:crypto';
export const canonicalStreet=s=>typeof s==='string'?s.replace(/(^|[\s.])(вул|просп|пров|пл|бульв|бул)\.(?=\S)/giu,'$1$2. '):s;
export const canonicalHouse=value=>String(value ?? '').normalize('NFKC').toLocaleLowerCase('uk').replace(/[\s№]/g,'').replace(/[aceopx]/g,c=>({a:'а',c:'с',e:'е',o:'о',p:'р',x:'х'})[c]).replace(/(\d)[‐‑‒–—-](?=[а-яіїєґ]$)/gu,'$1');
const name=value=>String(value??'').normalize('NFKC').toLocaleLowerCase('uk').replace(/[’ʼ`]/g,"'").replace(/\s+/g,' ').trim();
const locality=value=>name(value).replace(/^(?:(?:м|с|г)\.\s*|(?:місто|село|селище|смт)\s+)/u,'');
const sameGeography=(a,b)=>a.regionId===b.regionId&&locality(a.settlement)===locality(b.settlement)&&name(a.community)===name(b.community);
const streetKey=r=>JSON.stringify([r.regionId,locality(r.settlement),name(r.community),name(canonicalStreet(r.street))]);
const territoryKey=r=>JSON.stringify([r.regionId,locality(r.settlement),name(r.community)]);
const houseKey=(r,h)=>JSON.stringify([streetKey(r),canonicalHouse(h)]);
const compatible=(a,b)=>a.providerStreetId&&b.providerStreetId?a.providerStreetId===b.providerStreetId:!(a.officialCityId&&b.officialCityId&&a.officialCityId!==b.officialCityId);
const time=(r,b)=>Number.isFinite(r.checkedAt)?r.checkedAt:Number.isFinite(b.generatedAt)?b.generatedAt:0;
function add(index,key,row){if(!index.has(key))index.set(key,[]);index.get(key).push(row);}
function indexes(rows){const houses=new Map(),streets=new Map(),territories=new Map();for(const r of rows){if(r.scope==='house')for(const h of r.houses)add(houses,houseKey(r,h),r);else if(r.scope==='street')add(streets,streetKey(r),r);else if(r.scope==='settlement')add(territories,territoryKey(r),r);}return {houses,streets,territories};}
function covering(index,r,h){return [...(index.houses.get(houseKey(r,h))||[]),...(index.streets.get(streetKey(r))||[]),...(index.territories.get(territoryKey(r))||[])].filter(other=>(other.scope==='settlement'||compatible(other,r))&&!(other.excludedHouses||[]).some(value=>canonicalHouse(value)===canonicalHouse(h)));}
// Partial batches replace observations only when they are at least as recent as
// the retained fact. A late staging replay must not roll a newer queue backward.
// Negative house watermarks are publisher state, never runtime queue guesses.
export function mergeSnapshots(previous,fresh,now=Date.now()){
 const previousRows=(previous?.records||[]).filter(r=>r.expiresAt>now),oldIndex=indexes(previousRows),rawIndex=indexes(fresh.records);
 const freshAt=Number.isFinite(fresh.generatedAt)?fresh.generatedAt:now,watermarkIndex=new Map();
 for(const w of previous?.negativeHouseWatermarks||[])if(w.expiresAt>now)add(watermarkIndex,houseKey(w,w.house),w);
 const wmFor=(r,h)=>(watermarkIndex.get(houseKey(r,h))||[]).filter(w=>compatible(w,r));
 const selected=[];
 for(const r of fresh.records){
  if(r.scope==='house'){
   const houses=r.houses.filter(h=>!covering(oldIndex,r,h).some(old=>time(old,previous)>time(r,fresh))&&!wmFor(r,h).some(w=>w.checkedAt>=time(r,fresh)));
   if(houses.length)selected.push({...r,houses});
  }else{
   const comparable=previousRows.filter(old=>old.scope===r.scope&&sameGeography(old,r)&&(r.scope==='settlement'||streetKey(old)===streetKey(r)&&compatible(old,r)));
   if(!comparable.some(old=>time(old,previous)>time(r,fresh)))selected.push(r);
  }
 }
 const selectedIndex=indexes(selected),touched=new Set(fresh.completedStreetIds||[]),observations=[...(fresh.observedHouses||[])];
 // A completed authoritative street/operator read can explicitly remove an old
 // house absent from the new list. Its original snapshot time anchors that fact.
 for(const r of previousRows)if(r.scope==='house'&&(fresh.completeSnapshot||touched.has(r.officialCityId)))for(const h of r.houses)if(!covering(rawIndex,r,h).length)observations.push({...r,house:h,checkedAt:freshAt,expiresAt:Math.min(fresh.expiresAt||freshAt+86400000,freshAt+86400000)});
 for(const o of observations){
  if(covering(rawIndex,o,o.house).length)continue; // positive source observation
  const checkedAt=Number.isFinite(o.checkedAt)?o.checkedAt:freshAt,expiresAt=Math.min(Number.isFinite(o.expiresAt)?o.expiresAt:checkedAt+86400000,fresh.expiresAt||checkedAt+86400000,checkedAt+86400000);
  if(expiresAt<=now||checkedAt>now||covering(oldIndex,o,o.house).some(old=>time(old,previous)>checkedAt))continue;
  const w={regionId:o.regionId,settlement:o.settlement,community:o.community,street:o.street,house:o.house,checkedAt,expiresAt,...(o.providerStreetId?{providerStreetId:o.providerStreetId}:{}),...(o.officialCityId?{officialCityId:o.officialCityId}:{})},key=houseKey(w,w.house),old=watermarkIndex.get(key)||[];
  if(old.some(other=>compatible(other,w)&&other.checkedAt>=checkedAt))continue;
  watermarkIndex.set(key,[...old.filter(other=>!compatible(other,w)),w]);
 }
 const retained=[];
 for(const r of previousRows){
  const checkedAt=time(r,previous),fullRemoval=(fresh.completeSnapshot||touched.has(r.officialCityId))&&freshAt>=checkedAt;
  if(r.scope==='house'){
   const houses=r.houses.filter(h=>!fullRemoval&&!wmFor(r,h).some(w=>w.checkedAt>=checkedAt)&&!covering(selectedIndex,r,h).some(next=>time(next,fresh)>checkedAt||time(next,fresh)===checkedAt&&next.queue===r.queue));
   if(houses.length)retained.push({...r,houses});
  }else if(!fullRemoval&&!selected.some(next=>next.scope===r.scope&&sameGeography(next,r)&&(r.scope==='settlement'||streetKey(next)===streetKey(r)&&compatible(next,r))&&(time(next,fresh)>checkedAt||time(next,fresh)===checkedAt&&next.queue===r.queue)))retained.push(r);
 }
 const negativeHouseWatermarks=[];
 for(const list of watermarkIndex.values())for(const w of list)if(!covering(selectedIndex,w,w.house).some(r=>time(r,fresh)>w.checkedAt))negativeHouseWatermarks.push(w);
 // A source may reuse one row ID for a group whose unobserved members survive.
 // Re-key collisions instead of silently overwriting that retained group.
 const rows=new Map();for(const r of [...retained,...selected]){const existing=rows.get(r.id);if(existing&&JSON.stringify(existing)!==JSON.stringify(r)){rows.delete(r.id);const id='retained-'+createHash('sha256').update(JSON.stringify(existing)).digest('hex').slice(0,32);rows.set(id,{...existing,id});}rows.set(r.id,r);}
 const result=[...rows.values()];return {...fresh,generatedAt:now,expiresAt:Math.min(now+86400000,Math.max(now,...result.map(r=>r.expiresAt),...negativeHouseWatermarks.map(w=>w.expiresAt))),records:result,negativeHouseWatermarks};
}
// Existing client format supports explicit house lists. Group only observations
// with identical provenance and times; grouping never extends a single deadline.
export function compactSnapshot(bundle){
 const groups=new Map(),records=[];
 for(const r of bundle.records){
  if(r.scope!=='house'||r.quoteType!=='structured-official-fields'||r.excludedHouses?.length){records.push(r);continue;}
  const {id,quote,houses,...identity}=r;identity.street=canonicalStreet(identity.street);const k=JSON.stringify(identity);
  if(!groups.has(k))groups.set(k,{identity,houses:new Set()});for(const h of houses)groups.get(k).houses.add(h);
 }
 for(const [k,g] of groups){
  const houses=[...g.houses].sort();
  for(let i=0;i<houses.length;i+=40){const chunk=houses.slice(i,i+40),quote=`${g.identity.settlement}, ${g.identity.street}, будинки ${chunk.join(', ')}: черга ${g.identity.queue}`;
   if(quote.length>2500)throw Error('compact_quote_limit');
   records.push({...g.identity,id:'group-'+createHash('sha256').update(k+'|'+JSON.stringify(chunk)).digest('hex').slice(0,24),houses:chunk,quote});
  }
 }
 return {...bundle,records};
}
