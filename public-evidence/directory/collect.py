"""Free standard Chromium batch reader. No user address queries or evasion."""
import asyncio,json,pathlib,datetime,time,os,shutil,sys
from playwright.async_api import async_playwright
from reader import street_links,observe
ROOT=pathlib.Path(__file__).resolve().parents[1]
async def collect():
 config=json.loads((ROOT/'sources.json').read_text());state_path=ROOT/'directory-state.json';state=json.loads(state_path.read_text()) if state_path.exists() else {};now=int(time.time()*1000);deadline=time.monotonic()+6*60;accepted=[];read_urls=set();eligible={};report={'executionEnvironment':'github-actions' if os.environ.get('GITHUB_ACTIONS')=='true' else 'workspace','startedAt':now,'sources':[],'errors':[],'records':0}
 sources=json.loads((pathlib.Path(__file__).parent/'sources.json').read_text())
 if not sources:
  (ROOT/'directory-report.json').write_text(json.dumps({**report,'status':'disabled'},ensure_ascii=False,indent=2)+'\n');return
 executable=os.environ.get('SVITLO_BROWSER_BIN') or shutil.which('google-chrome') or shutil.which('chromium')
 async with async_playwright() as p:
  options={'headless':True,'args':['--no-sandbox']}
  if executable:options['executable_path']=executable
  proxy=os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY')
  if proxy:options['proxy']={'server':proxy}
  browser=await p.chromium.launch(**options)
  context=await browser.new_context();page=await context.new_page()
  async def read(url):
   response=await page.goto(url,wait_until='domcontentloaded',timeout=20000)
   if not response or response.status!=200:raise ValueError('HTTP '+str(response.status if response else 'none'))
   if page.url!=url:raise ValueError('Unexpected redirect')
   text=await page.content()
   if len(text)>2_000_000:raise ValueError('Page size limit')
   return text
  try:
   for source in sources[:4]:
    if time.monotonic()>deadline:break
    stats={'url':source['url'],'pages':0,'candidates':0,'accepted':0,'errors':[]};report['sources'].append(stats)
    try:
     links=street_links(await read(source['url']),source);eligible[source['url']]={x['url'] for x in links};stats['candidates']=len(links);stats['streetLimitReached']=len(links)>80
     cursor=state.get(source['url'],0)%len(links) if links else 0;selected=(links[cursor:]+links[:cursor])[:80];stats['startCursor']=cursor
     for link in selected:
      if time.monotonic()>deadline:stats['stopReason']='time_budget';break
      try:
       html=await read(link['url']);stats['pages']+=1;read_urls.add(link['url']);record=observe(html,link['url'],link['label'],source,now)
       if record:accepted.append(record);stats['accepted']+=1
      except Exception as e:stats['errors'].append({'url':link['url'],'error':str(e)[:180]})
     stats.setdefault('stopReason','street_limit' if len(links)>80 else 'complete');state[source['url']]=(cursor+len(selected))%len(links) if links else 0;stats['nextCursor']=state[source['url']]
    except Exception as e:stats['errors'].append({'url':source['url'],'error':str(e)[:180]})
  finally:await context.close();await browser.close()
 path=ROOT/'manifest.json';old=json.loads(path.read_text());assert old.get('schemaVersion')==2 and isinstance(old.get('records'),list)
 # Failed reads never renew an observation; successful rereads retract missing
 # or changed claims. Other readers' current records retain their provenance.
 records=[r for r in old['records'] if r.get('expiresAt',0)>now and not (r.get('evidenceType')=='address-directory' and (r.get('sourceUrl') in read_urls or r.get('observation',{}).get('listingUrl') in eligible and r.get('sourceUrl') not in eligible[r['observation']['listingUrl']]))]+accepted
 records=list({r['id']:r for r in records}.values())
 manifest={**old,'enabled':config.get('enabled') is True,'generatedAt':int(time.time()*1000),'records':records};body=json.dumps(manifest,ensure_ascii=False,indent=2)+'\n'
 if len(body.encode())>1_800_000 or len(records)>10000:raise ValueError('Complete manifest size budget exceeded')
 report.update(finishedAt=int(time.time()*1000),records=len(accepted),totalRuntimeRecords=len(records),status='current' if any(s['pages'] for s in report['sources']) else 'source_unavailable');(ROOT/'directory-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 if report['status']!='current':raise RuntimeError('No directory pages could be read; previous manifest was not refreshed')
 path.write_text(body);state_path.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':asyncio.run(collect())
