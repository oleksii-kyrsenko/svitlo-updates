import {createHash} from 'node:crypto';
export const canonicalStreet=s=>typeof s==='string'?s.replace(/(^|\s)(вул|просп|пров|пл|бульв|бул)\.(?=\S)/giu,'$1$2. '):s;
const key=(r,h)=>JSON.stringify([r.regionId,r.settlement,r.community,canonicalStreet(r.street),r.officialCityId||null,h]);
// Partial house batches replace only observed houses, never every house in a street.
export function mergeSnapshots(previous,fresh,now=Date.now()){
 const touched=new Set(fresh.completedStreetIds||[]),observed=new Set(fresh.records.filter(r=>r.scope==='house').flatMap(r=>r.houses.map(h=>key(r,h))));
 const retained=[];
 for(const r of previous?.records||[]){
  if(r.expiresAt<=now||touched.has(r.officialCityId))continue;
  if(r.scope==='house'){const houses=r.houses.filter(h=>!observed.has(key(r,h)));if(houses.length)retained.push({...r,houses});}
  else retained.push(r);
 }
 const rows=new Map();for(const r of [...retained,...fresh.records])rows.set(r.id,r);
 return {...fresh,generatedAt:now,expiresAt:Math.min(now+86400000,Math.max(now,...[...rows.values()].map(r=>r.expiresAt))),records:[...rows.values()]};
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
