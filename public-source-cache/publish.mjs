import {readFileSync,readdirSync,writeFileSync,mkdirSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
const gh=args=>execFileSync('gh',args,{encoding:'utf8'}),repo=process.env.GH_REPO,tag='source-cache-data';
let release;try{release=JSON.parse(gh(['api',`repos/${repo}/releases/tags/${tag}`]));}catch{}
if(!release){gh(['release','create',tag,'--repo',repo,'--prerelease','--title','Public operator document cache','--notes','Automatically collected public operator documents. No application sources, user searches, account identifiers or manual corrections.']);release=JSON.parse(gh(['api',`repos/${repo}/releases/tags/${tag}`]));}
const listAssets=()=>JSON.parse(gh(['api','--paginate','--slurp',`repos/${repo}/releases/${release.id}/assets?per_page=100`])).flat();
const present=listAssets();
for(const file of readdirSync('cache-output').filter(f=>f.endsWith('.json.gz'))){if(!present.some(a=>a.name===file))gh(['release','upload',tag,'cache-output/'+file,'--repo',repo]);}
const assets=listAssets();
const manifest=JSON.parse(readFileSync('cache-output/manifest.json'));
for(const entry of manifest.operators){const asset=assets.find(a=>a.browser_download_url===entry.url);if(!asset||asset.state!=='uploaded'||asset.size!==entry.size||asset.digest!=='sha256:'+entry.sha256)throw Error('Published bundle verification failed');}
mkdirSync('public-source-cache',{recursive:true});writeFileSync('public-source-cache/manifest.json',JSON.stringify(manifest,null,2)+'\n');
// Cleanup only after manifest publication, by a separate invocation.
if(process.argv.includes('--cleanup')){
 const referenced=new Set(manifest.operators.map(x=>x.url));
 for(const asset of assets)if(!referenced.has(asset.browser_download_url)&&Date.now()-Date.parse(asset.created_at)>48*3600000)gh(['api','--method','DELETE',`repos/${repo}/releases/assets/${asset.id}`]);
}
