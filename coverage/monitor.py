"""Bounded public source health and discovery; availability is not coverage."""
import argparse,concurrent.futures,datetime,hashlib,json,re,time,urllib.request,urllib.error
from html.parser import HTMLParser
from urllib.parse import urljoin,urlsplit
from pathlib import Path
MAX_BYTES=2_000_000
class Links(HTMLParser):
 def __init__(self,base):super().__init__();self.base=base;self.links=[]
 def handle_starttag(self,tag,attrs):
  values=dict(attrs);href=values.get('href','');url=urljoin(self.base,href)
  if tag=='a' and urlsplit(url).scheme=='https' and re.search(r't\.me/|\.pdf(?:\?|$)|\.xlsx(?:\?|$)|відключ|vidk|shutdown|blackout|черг|cherg',url,re.I):self.links.append(url)
def classify(status,text):
 if status in (403,429) or re.search(r'cf-chl-|challenge-platform|Incapsula incident|Request unsuccessful\. Incapsula|verify you are human',text,re.I):return 'source_protected'
 return 'page_available' if status==200 else 'source_unavailable'
def fetch(url):
 req=urllib.request.Request(url,headers={'User-Agent':'KolySvitloSourceMonitor/1.0 (+https://github.com/oleksii-kyrsenko/svitlo-updates)'})
 try:
  with urllib.request.urlopen(req,timeout=20) as r:
   data=r.read(MAX_BYTES+1)
   if len(data)>MAX_BYTES:raise ValueError('response_too_large')
   return r.status,r.geturl(),data
 except urllib.error.HTTPError as e:return e.code,url,b''
def probe(source,previous):
 started=time.monotonic();item={'operatorId':source['id'],'sourceUrl':source['sourceUrl'],'checkedAt':int(time.time()*1000)}
 try:
  status,url,data=fetch(source['sourceUrl']);text=data.decode('utf-8','replace');state=classify(status,text);parser=Links(url);parser.feed(text)
  item.update(status=state,httpStatus=status,sha256=hashlib.sha256(data).hexdigest(),bytes=len(data),leads=[{'url':u,'status':'needs_source_review'} for u in sorted(set(parser.links))[:40]])
 except Exception as e:item.update(status='source_unavailable',error=type(e).__name__)
 before=previous.get(source['id'],{});item['consecutiveFailures']=0 if item['status']=='page_available' else before.get('consecutiveFailures',0)+1
 item['regression']=before.get('status')=='page_available' and item['status']!='page_available'
 item['elapsedMs']=int((time.monotonic()-started)*1000);return item

def main():
 p=argparse.ArgumentParser();p.add_argument('--config',default='coverage/sources.json');p.add_argument('--output',default='coverage/report.json');p.add_argument('--registry',action='store_true');a=p.parse_args()
 cfg=json.loads(Path(a.config).read_text());old=json.loads(Path(a.output).read_text()) if Path(a.output).exists() else {};previous={r['operatorId']:r for r in old.get('operators',[])}
 with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:rows=list(pool.map(lambda s:probe(s,previous),cfg['operators']))
 report={'schemaVersion':1,'checkedAt':int(time.time()*1000),'method':'public-page-health-not-address-coverage','operators':rows,'counts':{s:sum(x['status']==s for x in rows) for s in sorted({x['status'] for x in rows})}}
 if a.registry:
  try:
   status,url,data=fetch(cfg['registryPage']);links=Links(url);links.feed(data.decode('utf-8','replace'));files=sorted(set(u for u in links.links if re.search(r'\.xlsx(?:\?|$)',u,re.I)))
   report['registry']={'pageUrl':url,'httpStatus':status,'discoveredRegisters':files,'reviewRequired':files!=old.get('registry',{}).get('discoveredRegisters',[]),'note':'Review license changes by legal identifier; do not infer an operator from a link.'}
  except Exception as e:report['registry']={'error':type(e).__name__,'reviewRequired':True}
 elif 'registry' in old:report['registry']=old['registry']
 Path(a.output).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report['counts']))
if __name__=='__main__':main()
