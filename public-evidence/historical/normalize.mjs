// Keep these exact identity rules aligned with shared/address-names.js in the
// application. No fuzzy matching, postal aliases or address/queue fixtures.
const types=[['lane',['провулок','пров.','прв.','переулок','пер.']],['drive',['проїзд','пр-д','проезд']],['dead-end',['тупик','туп.']],['avenue',['проспект','просп.','пр-т']],['boulevard',['бульвар','бульв.','бул.','б-р']],['square',['площа','пл.','площадь','майдан']],['highway',['шосе','шоссе','ш.']],['entrance',['в’їзд','вʼїзд','вїзд','въезд']],['descent',['узвіз','спуск']],['embankment',['набережна','наб.','набережная']],['',['вулиця','вул.','улица','ул.']]];
const escape=s=>s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
export function streetKey(value){
 let name=String(value||'').normalize('NFKC').toLocaleLowerCase('uk').replace(/[’'`ʼ]/g,'').replace(/\([^)]*\)/g,' ').replace(/[‐‑‒–—]/g,'-'),kind='';
 for(const [key,aliases] of types){const pattern=new RegExp('(^|\\s)(?:'+aliases.map(escape).join('|')+')(?=\\s|$)','gu');if(pattern.test(name)){if(key)kind=key;pattern.lastIndex=0;name=name.replace(pattern,' ');}}
 return name.replace(/[^\p{L}\p{N}]+/gu,' ').trim().replace(/\s+/g,' ')+(kind?'|'+kind:'');
}
let body='';for await(const chunk of process.stdin)body+=chunk;
if(body)process.stdout.write(JSON.stringify(JSON.parse(body).map(streetKey)));
