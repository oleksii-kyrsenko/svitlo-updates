import {readFileSync,writeFileSync,existsSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
const gh=(args)=>execFileSync('gh',args,{encoding:'utf8'});
const request=JSON.parse(readFileSync('.channel/release-request.json','utf8'));
const meta=request.meta;
if(request.schemaVersion!==1||!meta||!Number.isInteger(meta.versionCode)||meta.packageName!=='ua.svitlo.app.testing'||!/^\d+\.\d+\.\d+$/.test(meta.version)||!/^svitlo-test-\d+\.apk$/.test(meta.fileName)||!/^[a-f0-9]{64}$/.test(meta.sha256))throw new Error('Invalid release request');
const file='artifact/'+meta.fileName,bytes=readFileSync(file);
if(bytes.length!==meta.size||createHash('sha256').update(bytes).digest('hex')!==meta.sha256)throw new Error('APK checksum/size mismatch');
const signature=readFileSync('artifact/signature.txt','utf8');
const certificates=new Set([...signature.matchAll(/certificate SHA-256 digest:\s*([a-fA-F0-9]{64})/g)].map(match=>match[1].toLowerCase()));
const certificate=certificates.size===1?[...certificates][0]:null;
if(certificate!=='fac61745dc0903786fb9ede62a962b399f7348f0bb6f899b8332667591033b9c')throw new Error('Missing signing certificate verification');
if(existsSync('certificate.json')&&JSON.parse(readFileSync('certificate.json')).sha256!==certificate)throw new Error('Signing identity changed');
const tag='android-test-'+meta.versionCode,repository=process.env.GH_REPO;
let present;
try{present=JSON.parse(gh(['api',`repos/${repository}/releases/tags/${tag}`]));}catch{}
if(!present){
  const notes=`Світло ${meta.version}, Android-сборка ${meta.versionCode}.\n\n${meta.notes || ''}\n\nУстанавливайте поверх предыдущей версии. Исходный коммит APK: ${meta.sourceCommit}. Исходный код приложения находится в отдельном приватном репозитории.`;
  writeFileSync('artifact/RELEASE-NOTES.txt',notes);
  const assets=[file,'artifact/SHA256SUMS.txt','artifact/signature.txt'];if(existsSync('artifact/THIRD_PARTY_NOTICES.txt'))assets.push('artifact/THIRD_PARTY_NOTICES.txt');
  gh(['release','create',tag,...assets,'--repo',repository,'--target','main','--prerelease','--title',`Світло ${meta.version} — Android ${meta.versionCode}`,'--notes-file','artifact/RELEASE-NOTES.txt']);
}
const release=JSON.parse(gh(['api',`repos/${repository}/releases/tags/${tag}`]));
const asset=release.assets.find(asset=>asset.name===meta.fileName);
if(!asset||asset.state!=='uploaded'||asset.size!==meta.size||asset.digest!=='sha256:'+meta.sha256)throw new Error('Published APK failed verification');
const current=existsSync('latest.json')?JSON.parse(readFileSync('latest.json','utf8')):null;
if(!current||current.versionCode<=meta.versionCode){
  writeFileSync('latest.json',JSON.stringify({schemaVersion:1,packageName:meta.packageName,version:meta.version,versionCode:meta.versionCode,apkUrl:asset.browser_download_url,size:meta.size,sha256:meta.sha256,notes:meta.notes || '',services:current?.services || {reverse:'https://nominatim.openstreetmap.org/reverse',nearby:'https://overpass-api.de/api/interpreter'},publishedAt:new Date().toISOString(),sourceCommit:meta.sourceCommit},null,2)+'\n');
  writeFileSync('certificate.json',JSON.stringify({sha256:certificate},null,2)+'\n');
}
console.log('Published verified Android update',meta.version,meta.versionCode,asset.browser_download_url);
