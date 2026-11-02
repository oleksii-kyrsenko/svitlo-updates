// Rebuild signed indexes after a publisher code fix, without contacting a source
// or changing the observation times of previously collected official records.
import {readFile,writeFile} from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
import {resolve} from 'node:path';
import {previousSnapshot,combineSnapshots} from './refresh.mjs';
import {build,hash} from './build.mjs';
import {buildCityCoverage} from './build-v2.mjs';
import {legacyCompatibleBundles} from './legacy-compat.mjs';
export async function rebuildFromStaging({out='dynamic-coverage',staging='coverage/staging',reportFile='coverage/rebuild-report.json',keyFile=process.env.DYNAMIC_COVERAGE_KEY_FILE,now=Date.now(),dryRun=false}={}){
 const cfg=JSON.parse(await readFile('coverage/sources.json')),geography=JSON.parse(await readFile('coverage/capital-geography.json'));
 const previous=await previousSnapshot(out,now),collected=[],inputs=[],errors=[];
 for(const operator of cfg.operators){
  if(!/^[-a-z0-9]+$/.test(operator.id))throw Error('invalid_registry_operator');
  const file=resolve(staging,operator.id+'.json');if(!file.startsWith(resolve(staging)+'/'))throw Error('staging_path_escape');
  try{
   const raw=await readFile(file),snapshot=JSON.parse(raw);
   if(snapshot.operatorId!==operator.id)throw Error('staging_operator_mismatch');
   collected.push(snapshot);inputs.push({operatorId:operator.id,file:operator.id+'.json',sha256:hash(raw),generatedAt:snapshot.generatedAt,expiresAt:snapshot.expiresAt,records:snapshot.records?.length??null});
  }catch(error){if(error.code!=='ENOENT')errors.push({operatorId:operator.id,error:String(error.message||'invalid_staging_snapshot').slice(0,150)});}
 }
 const combined=combineSnapshots(previous.bundles,collected,now);errors.push(...combined.errors);
 const legacy=legacyCompatibleBundles(combined.bundles,previous.legacyBundles,now);
 const report={schemaVersion:1,generatedAt:now,method:'rebuild-from-retained-source-snapshots-without-network-or-observation-renewal',dryRun,inputs,errors,legacyConstraints:legacy.constraints,withdrawnOperators:combined.withdrawnOperators,revision:previous.revision,proposedLegacyOperators:legacy.bundles.length,proposedSourceOperators:combined.bundles.length,proposedSourceRecords:combined.bundles.reduce((n,b)=>n+b.records.length,0)};
 if(!combined.bundles.length&&!combined.withdrawnOperators.length){report.signing='no_valid_source_snapshots_previous_indexes_preserved';await writeFile(reportFile,JSON.stringify(report,null,2)+'\n');throw Error(report.signing);}
 if(!dryRun){
  if(!keyFile){report.signing='missing_key_previous_indexes_preserved';await writeFile(reportFile,JSON.stringify(report,null,2)+'\n');throw Error('Signing secret unavailable; indexes were not replaced');}
  let previousManifest=null;try{previousManifest=JSON.parse(await readFile(out+'/v2/manifest.json'));}catch(error){if(error.code!=='ENOENT')throw error;}
  const catalog={schemaVersion:1,generatedAt:now,expiresAt:now+86400000,operators:cfg.operators};
  report.publication=await build({catalog,bundles:legacy.bundles,revision:previous.revision,keyFile,out,now,allowEmptyPublication:legacy.constraints.length>0||combined.withdrawnOperators.length>0});
  report.cityPublication=await buildCityCoverage({catalog,bundles:combined.bundles,revision:previous.revision,keyFile,out:out+'/v2',geography,now,previousManifest,sourceSnapshots:combined.sourceSnapshots,allowEmptyPublication:combined.withdrawnOperators.length>0});
 }
 await writeFile(reportFile,JSON.stringify(report,null,2)+'\n');return report;
}
if(import.meta.url===pathToFileURL(process.argv[1]||'').href){
 if(process.argv.slice(2).some(arg=>arg!=='--dry-run'))throw Error('Usage: node coverage/rebuild-from-staging.mjs [--dry-run]');
 const report=await rebuildFromStaging({dryRun:process.argv.includes('--dry-run')});
 console.log(JSON.stringify({revision:report.revision,inputs:report.inputs.length,errors:report.errors,publication:report.publication,cities:report.cityPublication,dryRun:report.dryRun}));
}
