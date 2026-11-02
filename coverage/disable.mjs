// Prepare both signed generations together, then publish them in ONE Git commit.
// Offline clients keep the original deadline; a remote disable is not instant.
import {readFile,writeFile,mkdir,rename,rm} from 'node:fs/promises';
import {createPrivateKey,createPublicKey,sign,verify} from 'node:crypto';
import {pathToFileURL} from 'node:url';
export function prepareDisableEnvelopes({previousEnvelopes,privateKey,trustedPublicKey,now=Date.now()}){
 const actual=createPublicKey(privateKey);
 if(!actual.export({type:'spki',format:'der'}).equals(trustedPublicKey.export({type:'spki',format:'der'})))throw Error('wrong_signing_key');
 let maximum=0;
 for(const envelope of previousEnvelopes){
  if(!envelope)continue;
  const bytes=Buffer.from(envelope.payload||'','base64');
  if(![1,2].includes(envelope.schemaVersion)||envelope.keyId!=='coverage-v1'||bytes.length>2*1024*1024||!verify(null,bytes,trustedPublicKey,Buffer.from(envelope.signature||'','base64')))throw Error('unverified_previous_disable_manifest');
  const old=JSON.parse(bytes);
  if(old.schemaVersion!==envelope.schemaVersion||old.minClientVersion!==old.schemaVersion||!Number.isSafeInteger(old.revision)||old.revision<1)throw Error('invalid_previous_disable_revision');
  maximum=Math.max(maximum,old.revision);
 }
 if(!Number.isFinite(now)||now<=0||!Number.isSafeInteger(maximum+1))throw Error('invalid_disable_time_or_revision');
 const revision=maximum+1,envelopes=[1,2].map(schemaVersion=>{
  const value={schemaVersion,minClientVersion:schemaVersion,revision,enabled:false,generatedAt:now,expiresAt:now+86400000,bundles:[],...(schemaVersion===2?{retiredCities:[],sourceSnapshots:[]}:{})};
  const payload=Buffer.from(JSON.stringify(value)),signature=sign(null,payload,privateKey);
  if(!verify(null,payload,trustedPublicKey,signature))throw Error('disable_self_verification_failed');
  return {schemaVersion,keyId:'coverage-v1',payload:payload.toString('base64'),signature:signature.toString('base64')};
 });
 return {revision,envelopes};
}
export async function disableCoverage({out='dynamic-coverage',keyFile,now=Date.now()}={}){
 if(!keyFile)throw Error('Set DYNAMIC_COVERAGE_KEY_FILE to protected signing file');
 const privateKey=createPrivateKey(await readFile(keyFile)),trustedPublicKey=createPublicKey(await readFile(new URL('./public.pem',import.meta.url)));
 const files=[out+'/manifest.json',out+'/v2/manifest.json'],originals=[];
 for(const file of files){try{originals.push(await readFile(file));}catch(error){if(error.code!=='ENOENT')throw error;originals.push(null);}}
 const result=prepareDisableEnvelopes({previousEnvelopes:originals.map(raw=>raw?JSON.parse(raw):null),privateKey,trustedPublicKey,now});
 await mkdir(out+'/v2',{recursive:true});const staged=files.map(file=>file+'.disable.tmp');
 try{
  // Complete signature/schema preparation before either active file changes.
  await Promise.all(staged.map((file,i)=>writeFile(file,JSON.stringify(result.envelopes[i],null,2)+'\n')));
  try{for(let i=0;i<files.length;i++)await rename(staged[i],files[i]);}
  catch(error){for(let i=0;i<files.length;i++){if(originals[i])await writeFile(files[i],originals[i]);else await rm(files[i],{force:true});}throw error;}
 }finally{await Promise.all(staged.map(file=>rm(file,{force:true})));}
 return {revision:result.revision,disabledProtocols:[1,2],files};
}
if(import.meta.url===pathToFileURL(process.argv[1]||'').href){
 const result=await disableCoverage({keyFile:process.env.DYNAMIC_COVERAGE_KEY_FILE});
 console.log(JSON.stringify({...result,note:'Commit and push BOTH manifests in one Git commit; neither APK nor signing key is changed.'}));
}
