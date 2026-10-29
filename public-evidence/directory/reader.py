"""Live public street directory observations; never operator confirmations."""
import datetime,hashlib,json,re,urllib.parse,unicodedata
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup
KYIV=ZoneInfo('Europe/Kyiv')
def plain(s):return re.sub(r'\s+',' ',s.replace('+',' ')).strip()
def route(url):
 u=urllib.parse.urlsplit(url)
 if u.scheme!='https' or u.username or u.password or u.port not in (None,443) or u.query or u.fragment:return None
 parts=[urllib.parse.unquote(x) for x in u.path.strip('/').split('/')]
 return u,parts

def street_identity(label):
 s=unicodedata.normalize('NFKC',label).lower();s=re.sub(r"[’ʼ'`]",'',s);s=re.sub(r'\([^)]*\)',' ',s);s=re.sub(r'\d.*$',' ',s);s=re.sub(r'\b(?:непарні|парні|частково|частина|крім|окрім)\b.*$',' ',s)
 kinds=[('lane',r'провулок|пров\.|переулок|пер\.'),('avenue',r'проспект|просп\.|пр-т'),('boulevard',r'бульвар|бульв\.'),('square',r'площа|пл\.'),('highway',r'шосе'),('street',r'вулиця|вул\.|улица|ул\.')]
 kind='street';typed=False
 for key,pattern in kinds:
  regex=r'(?<!\w)(?:'+pattern+r')(?!\w)'
  if re.search(regex,s):kind=key;typed=True;s=re.sub(regex,' ',s)
 return re.sub(r'[^\w]+',' ',s).strip(),kind,typed

def street_links(body,source):
 soup=BeautifulSoup(body,'html.parser');title=soup.select_one('h1');expected='Графік відключення електроенергії '+source['sourceSettlement']+' ('+source['regionName']+')'
 if not title or plain(title.get_text(' ',strip=True))!=expected:raise ValueError('Directory geography/title changed')
 entries={}
 for a in soup.select('a[href]'):
  url=urllib.parse.urljoin(source['url'],a['href']);parsed=route(url)
  if not parsed:continue
  u,p=parsed
  if u.hostname!=urllib.parse.urlsplit(source['url']).hostname or len(p)!=3 or p[0] not in ('grafik','select') or plain(p[1])!=source['sourceSettlement']:continue
  label=a.get_text(' ',strip=True)
  if not label or plain(p[2])!=label:continue
  entries[url]={'url':url,'label':label,'route':p[0],'identity':street_identity(label)}
 blocked=set()
 for row in entries.values():
  if re.search(r'[,;]',row['label']):
   blocked.update(street_identity(part)[0] for part in re.split(r'[,;]',row['label']) if street_identity(part)[0])
 out=[]
 for row in entries.values():
  if row['route']!='grafik' or re.search(r'\d|[,;]|непарн|парн|частин|частково|крім|окрім',row['label'],re.I):continue
  base,kind,typed=row['identity'];same=[r for r in entries.values() if r['identity'][:2]==(base,kind)]
  # Inspect the COMPLETE locality index before publishing any street scope.
  # An alias needing house selection or another same-kind spelling invalidates
  # a blanket assignment; an untyped name cannot choose between street types.
  if not base or base in blocked or len(same)!=1 or not typed and sum(r['identity'][0]==base for r in entries.values())!=1:continue
  out.append({'url':row['url'],'label':row['label']})
 return out

def observe(body,url,label,source,now):
 parsed=route(url)
 if not parsed:return None
 u,p=parsed
 if u.hostname!='energy-ua.info' or len(p)!=3 or p[0]!='grafik' or plain(p[1])!=source['sourceSettlement'] or plain(p[2])!=label:return None
 # A house-selection page is never turned into a whole-street assignment.
 if re.search(r'\d|[,;]|непарн|парн|частин|частково|крім|окрім',label,re.I):return None
 soup=BeautifulSoup(body,'html.parser');h=soup.select_one('h1');q=soup.select('.ch_num_info');dates=soup.select('.scale_info_ch_date')
 title=h.get_text(' ',strip=True) if h else '';expected='Графік відключення електроенергії '+source['sourceSettlement']+', '+label
 if title!=expected or len(q)!=1 or not dates:return None
 queue_label=q[0].get_text(' ',strip=True);m=re.fullmatch(r'У вас\s+(\d{1,2})\s+черга\s*\(\s*(\d{1,2})\s+підгрупа\s*\)\s*-\s*після підключення сповіщень орієнтуйтесь на неї!',queue_label)
 d=re.search(r'\b(\d{2}\.\d{2}\.\d{4})\b',dates[0].get_text(' ',strip=True))
 if not m or not d:return None
 try:as_of=datetime.datetime.strptime(d[1],'%d.%m.%Y').date()
 except ValueError:return None
 current=datetime.datetime.fromtimestamp(now/1000,KYIV)
 if as_of!=current.date():return None
 expiry=min(now+12*3600000,int(datetime.datetime.combine(as_of+datetime.timedelta(days=1),datetime.time(),KYIV).timestamp()*1000))
 record={'recordVersion':3,'evidenceType':'address-directory','operatorId':source['operatorId'],'regionId':source['regionId'],'community':source['community'],'settlement':source['settlement'],'street':label,'scope':'street','queue':m[1]+'.'+m[2],'quote':title,'sourceUrl':url,'publishedAt':None,'fetchedAt':now,'expiresAt':expiry,'sourceContext':{'verified':True,'settlement':source['settlement'],'community':source['community'],'regionId':source['regionId'],'quote':title,'basisUrl':source['geographyBasisUrl']},'observation':{'method':'browser-directory','addressTitle':title,'queueLabel':queue_label,'asOfDate':as_of.isoformat(),'listingUrl':source['url'],'listingLabel':label}}
 record['id']=hashlib.sha256(json.dumps({k:v for k,v in record.items() if k not in ('fetchedAt','expiresAt')},sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:32]
 return record
