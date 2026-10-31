export function mergeSnapshots(previous,fresh,now=Date.now()){
 const touched=new Set(fresh.completedStreetIds||[]);
 const retained=(previous?.records||[]).filter(r=>r.expiresAt>now&&!touched.has(r.officialCityId));
 const rows=new Map();for(const r of [...retained,...fresh.records])rows.set(r.id,r);
 return {...fresh,generatedAt:now,expiresAt:Math.min(now+86400000,Math.max(now,...[...rows.values()].map(r=>r.expiresAt))),records:[...rows.values()]};
}
