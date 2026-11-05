// Stage only files authenticated by the two current signed indexes.
import {readFile} from 'node:fs/promises';
import {existsSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
const prefix='https://raw.githubusercontent.com/oleksii-kyrsenko/svitlo-updates/main/';
const files=new Set(['dynamic-coverage/manifest.json','dynamic-coverage/v2/manifest.json']);
for(const path of [...files]){
 const envelope=JSON.parse(await readFile(path)),manifest=JSON.parse(Buffer.from(envelope.payload,'base64'));
 for(const entry of [...manifest.bundles,...(manifest.sourceSnapshots||[])]){
  if(!entry.url.startsWith(prefix))throw Error('untrusted_publication_url');
  const file=entry.url.slice(prefix.length);
  if(!/^dynamic-coverage\/(?:v2\/)?(?:bundles|sources)\/[a-f0-9]{64}\.json$/.test(file)||!existsSync(file))throw Error('invalid_publication_file');
  files.add(file);
 }
}
execFileSync('git',['add','--',...files]);
console.log(JSON.stringify({stagedReferencedFiles:files.size}));
