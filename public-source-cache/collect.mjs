// Public-data collector only. Application resolvers and user requests are absent.
import {readFileSync,writeFileSync,mkdirSync,existsSync,unlinkSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {gzipSync} from 'node:zlib';
import {execFileSync} from 'node:child_process';
import {load} from 'cheerio';
const sources=JSON.parse(readFileSync(new URL('./sources.json',import.meta.url))),out='cache-output';mkdirSync(out,{recursive:true});
const now=Date.now(),maxAge=12*3600000,MAX=16*1024*1024;
const hash=b=>createHash('sha256').update(b).digest('hex');
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function publicURL(value){const u=new URL(value);if(u.protocol!=='https:'||u.username||u.password||u.hash)throw Error('invalid_source_url');return u;}
async function get(url){
 let target=publicURL(url);const origin=target.origin;
 const signal=AbortSignal.timeout(30000);
 for(let redirects=0;redirects<4;redirects++){
  const r=await fetch(target,{signal,redirect:'manual',headers:{'User-Agent':'SvitloPublicDocuments/1 https://github.com/oleksii-kyrsenko/svitlo-updates','Accept-Language':'uk','Cache-Control':'no-cache'}});
  if([301,302,303,307,308].includes(r.status)){const next=publicURL(new URL(r.headers.get('location'),target).href);if(next.origin!==origin)throw Error('cross_origin_redirect');target=next;continue;}
  if(!r.ok)throw Error('source_http_'+r.status);
  if(Number(r.headers.get('content-length'))>MAX)throw Error('source_too_large');
  let length=0;const chunks=[];for await(const chunk of r.body){length+=chunk.length;if(length>MAX)throw Error('source_too_large');chunks.push(chunk);}
  const bytes=Buffer.concat(chunks);if(bytes.length<1)throw Error('empty_source');return bytes;
 }throw Error('source_redirect_limit');
}
function html(bytes,base){
 const text=bytes.toString('utf8');if(/_Incapsula_Resource|cf-chl-|<title>[^<]*(?:captcha|Just a moment)/i.test(text))throw Error('source_protected');
 const $=load(text),links=[];
 $('a[href]').each((_,a)=>{try{const u=publicURL(new URL($(a).attr('href'),base).href);links.push({url:u.href,label:$(a).text().replace(/\s+/g,' ').trim()});}catch{}});
 // Preserve public links and cell text, without scripts, forms, CSRF or cookies.
 const anchors=links.map(a=>`<a href="${esc(a.url)}">${esc(a.label)}</a>`).join('\n');
 const tables=[];$('table').each((_,t)=>{const rows=[];$(t).find('tr').each((_,tr)=>{const cells=[];$(tr).children('td,th').each((_,c)=>cells.push(`<${c.tagName}>${esc($(c).text().replace(/\s+/g,' ').trim())}</${c.tagName}>`));rows.push('<tr>'+cells.join('')+'</tr>');});tables.push('<table>'+rows.join('')+'</table>');});
 const pages=[];for(const m of text.matchAll(/pageUrl\s*:\s*"((?:\\.|[^"\\])*)"/g)){try{const value=JSON.parse('"'+m[1].replace(/\\x([0-9a-f]{2})/gi,'\\u00$1')+'"');pages.push(publicURL(new URL(value,base).href).href);}catch{}}
 return {links,pages,text:'<html><body>'+anchors+tables.join('')+pages.map(u=>'\npageUrl: '+JSON.stringify(u)).join('')+'</body></html>'};
}
// Generic axis-aligned PDF graphics rectangles in page coordinates.
function rectangles(list,OPS){
 const stack=[],boxes=[];let m=[1,0,0,1,0,0];
 for(let i=0;i<list.fnArray.length;i++){
  const op=list.fnArray[i],v=list.argsArray[i];
  if(op===OPS.save)stack.push(m.slice());
  else if(op===OPS.restore)m=stack.pop()||[1,0,0,1,0,0];
  else if(op===OPS.transform){const [a,b,c,d,e,f]=m,[g,h,j,k,l,n]=v;m=[a*g+c*h,b*g+d*h,a*j+c*k,b*j+d*k,a*l+c*n+e,b*l+d*n+f];}
  else if(op===OPS.constructPath&&m[1]===0&&m[2]===0&&v[0].length===1&&v[0][0]===OPS.rectangle){
   const [x,y,w,h]=v[1],left=m[0]*x+m[4],right=m[0]*(x+w)+m[4],bottom=m[3]*y+m[5],top=m[3]*(y+h)+m[5];
   if(Math.abs(right-left)>10&&Math.abs(top-bottom)>2)boxes.push({x:Math.min(left,right),y:Math.min(bottom,top),width:Math.abs(right-left),height:Math.abs(top-bottom)});
   if(boxes.length>30000)throw Error('too_many_rectangles');
  }
 }return boxes;
}
let pdfjs;
async function document(bytes,kind){
 if(kind==='xlsx'){
  const path=out+'/input.xlsx';writeFileSync(path,bytes);
  try{return JSON.parse(execFileSync('python3',['public-source-cache/xlsx.py',path],{encoding:'utf8',maxBuffer:32*1024*1024,timeout:90000}));}finally{unlinkSync(path);}
 }
 if(bytes.subarray(0,5).toString()!=='%PDF-')throw Error('invalid_pdf');
 pdfjs??=await import('pdfjs-dist/legacy/build/pdf.mjs');const task=pdfjs.getDocument({data:new Uint8Array(bytes),isEvalSupported:false,disableFontFace:true,useSystemFonts:false,stopAtErrors:true});
 try{
  const pdf=await task.promise;if(pdf.numPages<1||pdf.numPages>160)throw Error('page_limit');const pages=[];let chars=0;
  for(let n=1;n<=pdf.numPages;n++){
   const p=await pdf.getPage(n),v=p.getViewport({scale:1}),content=await p.getTextContent();
   const items=content.items.filter(x=>typeof x.str==='string'&&x.str.trim()).map(x=>{chars+=x.str.length;if(chars>2000000)throw Error('text_limit');return {text:x.str,x:x.transform[4],y:x.transform[5],width:x.width,height:x.height};});
   if(items.length>10000)throw Error('page_text_limit');pages.push({number:n,width:v.width,height:v.height,items,rectangles:rectangles(await p.getOperatorList(),pdfjs.OPS)});p.cleanup();
  }return {pages};
 }finally{await task.destroy();}
}
const months=['січня','лютого','березня','квітня','травня','червня','липня','серпня','вересня','жовтня','листопада','грудня'];
const today=new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/Kyiv',year:'numeric',month:'2-digit',day:'2-digit'}).format(now);
function currentPeriod(label){const m=label.match(/з\s+(\d{1,2})\s+([а-яіїєґ]+)\s+(\d{4})\s*(?:р\.?)?\s*по\s+(\d{1,2})\s+([а-яіїєґ]+)\s+(\d{4})/iu);if(!m)return false;const d=(a,b,c)=>`${c}-${String(months.indexOf(b.toLowerCase())+1).padStart(2,'0')}-${a.padStart(2,'0')}`;return d(m[1],m[2],m[3])<=today&&today<=d(m[4],m[5],m[6]);}
const manifest={schemaVersion:1,generatedAt:now,operators:[],failures:[]};
const previous=existsSync('public-source-cache/manifest.json')?JSON.parse(readFileSync('public-source-cache/manifest.json')):null;
for(const [operatorId,config] of Object.entries(sources)){
 try{
  const fetchedAt=Date.now();
  const origin=new URL(config.index).origin,resources=[],seen=new Set();
  const page=async url=>{if(seen.has(url))throw Error('duplicate_page');seen.add(url);const bytes=await get(url),parsed=html(bytes,url);resources.push({url,kind:'text',sourceSha256:hash(bytes),value:{text:parsed.text}});return parsed;};
  const index=await page(new URL(config.index).href);
  if(config.extension){
   let docs=index.links.filter(a=>{const u=new URL(a.url);return u.origin===origin&&u.pathname.startsWith(config.prefix)&&u.pathname.endsWith(config.extension)&&!u.search;});
   if(operatorId==='cherkasy')docs=docs.filter(a=>currentPeriod(a.label));
   if(operatorId==='khmelnytskyi')docs=docs.filter(a=>/черги\s+гпв/iu.test(a.label));
   if(operatorId==='rivne')docs=docs.filter(a=>/чергу.*області/iu.test(a.label));
   docs=[...new Map(docs.map(d=>[d.url,d])).values()];if(!docs.length||docs.length>36)throw Error('document_count');
   for(const {url} of docs){const bytes=await get(url);resources.push({url,kind:'document',sourceSha256:hash(bytes),value:await document(bytes,config.extension.slice(1))});}
  }else{
   const children=index.links.filter(a=>new URL(a.url).origin===origin&&!new URL(a.url).search&&/перелік.*адрес/iu.test(a.label));if(children.length>4)throw Error('child_page_count');
   const links=[...index.links];for(const a of [...new Map(children.map(a=>[a.url,a])).values()])links.push(...(await page(a.url)).links);
   const sheets=[];for(const a of links){const u=new URL(a.url);if(u.origin!=='https://docs.google.com'||!/^\/spreadsheets\/d\/[\w-]+\/(?:edit|htmlview)$/.test(u.pathname)||!/черга/iu.test(a.label))continue;u.pathname=u.pathname.replace(/\/edit$/,'/htmlview');u.search='';sheets.push(u.href);}
   const unique=[...new Set(sheets)];if(!unique.length||unique.length>30)throw Error('sheet_count');
   for(const url of unique){const shell=await page(url);for(const target of [...new Set(shell.pages)]){const u=new URL(target),base=new URL(url);if(u.origin!==base.origin||!/^\/spreadsheets\/d\/[\w-]+\/htmlview\/sheet$/.test(u.pathname)||u.pathname.split('/')[3]!==base.pathname.split('/')[3]||[...u.searchParams.keys()].some(k=>!['headers','gid'].includes(k)))throw Error('invalid_sheet_child');if(!seen.has(u.href))await page(u.href);}}
  }
  if(resources.length>100)throw Error('resource_count');
  const data=Buffer.from(JSON.stringify({schemaVersion:1,operatorId,resources}));if(data.length>32*1024*1024)throw Error('bundle_size');const gzip=gzipSync(data,{level:9});if(gzip.length>8*1024*1024)throw Error('compressed_size');
  const sha256=hash(gzip),fileName=operatorId+'-'+sha256+'.json.gz';writeFileSync(out+'/'+fileName,gzip);
  manifest.operators.push({operatorId,fetchedAt,expiresAt:fetchedAt+maxAge,sha256,size:gzip.length,decodedSize:data.length,url:`https://github.com/${process.env.GITHUB_REPOSITORY||'oleksii-kyrsenko/svitlo-updates'}/releases/download/source-cache-data/${fileName}`});
  console.log(operatorId,'OK',resources.length,'public resources',gzip.length,'compressed bytes');
 }catch(error){
  const reason=/^[a-z0-9_]+$/i.test(error.message)?error.message:'collection_failed';manifest.failures.push({operatorId,reason});console.log('::warning::'+operatorId+': '+reason);
  const old=previous?.operators?.find(x=>x.operatorId===operatorId);if(old&&old.fetchedAt<=now&&now-old.fetchedAt<maxAge)manifest.operators.push(old);
 }
}
if(!manifest.operators.length)throw Error('No current complete operator bundle; previous manifest was not changed');
writeFileSync(out+'/manifest.json',JSON.stringify(manifest,null,2)+'\n');
