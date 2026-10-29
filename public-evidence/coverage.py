"""Grounded address grammar and section-roster reader. No address/queue fixtures."""
import re,datetime,hashlib,json
from bs4 import BeautifulSoup
from zoneinfo import ZoneInfo
DAY=86400000
UKR=r'А-Яа-яІіЇїЄєҐґA-Za-z'
HOUSE=r'\d{1,4}['+UKR+r']?(?:/\d{1,4}['+UKR+r']?)?'
RANGE=HOUSE+r'\s*[-–—]\s*'+HOUSE+r'(?:\s*\(?(?:непарні|парні|усі)\)?)?'
SELECTOR=r'(?:'+RANGE+'|'+HOUSE+r')'
def parse_houses(text):
 """Consume the entire selector; never silently discard an unknown qualifier."""
 s=text.strip().strip(',; ');parts=re.split(r'\s*(?:крім|окрім|за винятком)\s*',s,maxsplit=1,flags=re.I)
 def entries(v):
  out=[]
  for x in re.split(r'\s*[,;]\s*',v):
   x=x.strip()
   if x and not re.fullmatch(SELECTOR,x,re.I):return None
   if x:out.append(x)
  return out
 values=entries(parts[0]);exclude=entries(parts[1]) if len(parts)>1 else []
 if values is None or exclude is None or not values or any(re.search('[-–—]',x) for x in exclude):return None
 houses=[];ranges=[]
 for x in values:
  if re.search('[-–—]',x):
   m=re.fullmatch('('+HOUSE+r')\s*[-–—]\s*('+HOUSE+r')(.*)',x,re.I);a,b=int(re.match(r'\d+',m[1])[0]),int(re.match(r'\d+',m[2])[0])
   if a>b or b-a>5000:return None
   ranges.append(x)
  else:houses.append(x)
 return {'houses':houses,'houseRanges':ranges,'excludedHouses':exclude}
def timestamp(text):
 dt=datetime.datetime.fromisoformat(text.strip().replace('Z','+00:00'))
 if dt.tzinfo is None:
  if len(text.strip())!=10:raise ValueError('Missing timezone')
  dt=dt.replace(tzinfo=ZoneInfo('Europe/Kyiv'))
 return int(dt.timestamp()*1000)
def published_at(soup):
 for tag in soup.find_all('meta'):
  if tag.get('property') in ('article:published_time','og:published_time') or tag.get('itemprop')=='datePublished':
   try:return timestamp(tag.get('content',''))
   except ValueError:pass
 for tag in soup.find_all('script',type='application/ld+json'):
  for value in re.findall(r'"datePublished"\s*:\s*"([^"]+)"',tag.get_text()):
   try:return timestamp(value)
   except ValueError:pass
 # Read the article's own date; never a generic sidebar/footer <time>.
 for tag in soup.select('time[itemprop="datePublished"], time.entry-date, time.content-date[datetime]'):
  try:return timestamp(tag.get('datetime',''))
  except ValueError:pass
 return None

def validity(text):
 # An explicit publisher period is evidence; retrieval time alone never is.
 m=re.search(r'[^.!?\n]{0,100}(?:діють|діятимуть|чинні|діє)[^\n]{0,70}?з\s+(\d{1,2}[./]\d{1,2}[./]20\d{2})\s*(?:року\s*)?(?:до|по)\s*(\d{1,2}[./]\d{1,2}[./]20\d{2})(?:\s*року)?',text,re.I)
 if not m:return None
 def iso(s):return datetime.datetime.strptime(s.replace('/','.'),'%d.%m.%Y').date().isoformat()
 try:
  a,b=iso(m[1]),iso(m[2]);span=(datetime.date.fromisoformat(b)-datetime.date.fromisoformat(a)).days
  if not 0<span<=370:return None
  return {'from':a,'to':b,'quote':m[0].strip()}
 except ValueError:return None

def parse_roster(html,source,now):
 soup=BeautifulSoup(html,'html.parser');article=soup.select_one('article .entry-content, article .post-content, .entry-content, article') or soup
 published=published_at(soup)
 if not published or published>now:return []
 period=validity(article.get_text(' ',strip=True));records=[]
 headings=article.find_all(['h2','h3','h4'])
 for heading in headings:
  title=heading.get_text(' ',strip=True);m=re.fullmatch(r'(\d{1,2})\s*черга\s*(\d{1,2})\s*підчерга',title,re.I)
  if not m:continue
  chunks=[]
  for el in heading.next_siblings:
   if getattr(el,'name',None) in ('h2','h3','h4'):break
   chunks.append(el.get_text(' ',strip=True) if hasattr(el,'get_text') else str(el))
  text=re.sub(r'\s+',' ',' '.join(chunks));queue=m[1]+'.'+m[2]
  markers=list(re.finditer(r'(?<!\w)(?:м\.|с\.|смт\.)\s*',text,re.I))
  for i,marker in enumerate(markers):
   city=source.get('settlement','')
   if not city or not re.match(re.escape(city)+r'(?!['+UKR+r'])',text[marker.end():]):continue
   city_end=marker.end()+len(city)
   block=text[city_end:markers[i+1].start() if i+1<len(markers) else len(text)]
   pattern=r'(?P<street>['+UKR+r'’ʼ\-][ '+UKR+r'’ʼ.\-]{1,90}?),\s*(?P<selector>'+SELECTOR+r'(?:\s*[,;]\s*'+SELECTOR+r')*)'
   kind='вулиця'
   for item in re.finditer(pattern,block,re.I):
    street=item['street'].strip();selectors=item['selector'].strip(' ,;');tail=block[item.end():].lstrip(' ,;')
    if re.match(r'\(?(?:крім|окрім|частин|частково|не всі|вибірково|непарні|парні|за винятком|під[’\']?їзд)',tail,re.I):continue
    prefix=block[max(0,item.start()-10):item.start()]
    explicit=re.search(r'(?:^|\s)(вул\.|пров\.|просп\.|бульв\.)\s*(.*)$',street)
    if explicit:kind={'вул.':'вулиця','пров.':'провулок','просп.':'проспект','бульв.':'бульвар'}[explicit[1]];street=explicit[2].strip()
    # Drop prose/object names. A shortened surname remains a source spelling;
    # the phone needs a real postal alias to match a longer renamed street.
    if not street or len(street.split())>5 or re.search(r'Абонент|ТП-|школ|садок|ТОВ|ПАТ|КП |вул\.',street,re.I):continue
    parsed=parse_houses(selectors)
    if not parsed:continue
    quote=item.group(0).strip()
    r={'recordVersion':2,'operatorId':source['operatorId'],'regionId':source['regionId'],'community':source['community'],'settlement':city,'street':kind+' '+street,'scope':'house','queue':queue,**parsed,'quote':quote,'queueQuote':title,'evidenceType':'section-roster','sourceUrl':source['url'],'publishedAt':published,'fetchedAt':now,'sourceContext':{'verified':True,'settlement':city,'community':source['community'],'regionId':source['regionId'],'quote':text[marker.start():city_end],'basisUrl':source['url']}}
    # The canonical type is metadata; source quote may omit it in continuation lists.
    if period:r['validity']=period
    deadline=published+7*DAY
    if period and period['from']<=datetime.datetime.fromtimestamp(now/1000,ZoneInfo('Europe/Kyiv')).date().isoformat()<period['to']:
     deadline=min(now+7*DAY,timestamp(period['to']))
    if period and not period['from']<=datetime.datetime.fromtimestamp(now/1000,ZoneInfo('Europe/Kyiv')).date().isoformat()<period['to']:deadline=min(now,published)
    r['expiresAt']=deadline
    r['id']=hashlib.sha256(json.dumps({k:v for k,v in r.items() if k not in ('fetchedAt','expiresAt')},sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:32]
    records.append(r)
 return records
