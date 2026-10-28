"""Free, bounded source discovery. Search results are leads, never queue facts."""
import re,urllib.parse,xml.etree.ElementTree as ET
from bs4 import BeautifulSoup

def relevant(title,url,terms):
 text=(title+' '+urllib.parse.unquote(url)).casefold()
 return any(re.search(r'(?<!\w)'+re.escape(t.casefold())+r'(?!\w)',text) for t in terms if len(t)>3)
def search_sources(query,terms,fetch,limit=8):
 page,_,_=fetch('https://html.duckduckgo.com/html/?q='+urllib.parse.quote(query))
 soup=BeautifulSoup(page,'html.parser');results=[];rejected=0
 for anchor in soup.select('a.result__a'):
  url=urllib.parse.urljoin('https://duckduckgo.com',anchor.get('href',''));u=urllib.parse.urlsplit(url)
  if u.hostname and u.hostname.endswith('duckduckgo.com'):url=urllib.parse.parse_qs(u.query).get('uddg',[''])[0]
  title=anchor.get_text(' ',strip=True)
  if not url.startswith('https://') or not relevant(title,url,terms):rejected+=1;continue
  results.append({'url':url,'title':title,'query':query,'status':'needs_source_review'})
 return {'query':query,'results':results[:limit],'irrelevantDiscarded':rejected}
def discover_links(html,url):
 soup=BeautifulSoup(html,'html.parser');found=[]
 for a in soup.find_all('a',href=True):
  target=urllib.parse.urljoin(url,a['href']);u=urllib.parse.urlsplit(target);title=a.get_text(' ',strip=True)
  if u.hostname in ('t.me','telegram.me') and re.fullmatch(r'/(?:s/)?[A-Za-z][\w]{3,}',u.path) and not u.path.lower().endswith('bot'):
   channel=u.path.split('/')[-1];found.append({'url':'https://t.me/s/'+channel,'title':title,'discoveredFrom':url,'status':'needs_geographic_review'})
  elif u.scheme=='https' and (re.search(r'відключ|електроен|знеструм|черг[аиу]\b|підчерг',title,re.I) or re.search(r'vidkliuch|vidklyuch|cherg|cherh|blackout|\.pdf$|\.xlsx$',u.path,re.I)):
   if not re.search('квартир|дитсад|екобус|прийом|чергуван',title,re.I):found.append({'url':target,'title':title,'discoveredFrom':url,'status':'needs_document_review'})
 return list({x['url']:x for x in found}.values())[:60]
