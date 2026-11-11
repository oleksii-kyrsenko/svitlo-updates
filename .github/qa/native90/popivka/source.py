"""Independent public-source observation for schedule QA, not application code."""
from html.parser import HTMLParser
from urllib.parse import urljoin,urlsplit
import datetime,hashlib,json,pathlib,re,urllib.request,zoneinfo
HOME='https://www.cherkasyoblenergo.com/'
MONTHS=['січня','лютого','березня','квітня','травня','червня','липня','серпня','вересня','жовтня','листопада','грудня']
QUEUES={str(q)+'.'+str(s) for q in range(1,7) for s in [1,2]}
class Document(HTMLParser):
 def __init__(self):
  super().__init__(convert_charrefs=True);self.text=[];self.links=[];self.link=None;self.title=[];self.h1=False;self.skip=0
 def handle_starttag(self,tag,attrs):
  if tag in ['script','style']:self.skip+=1
  if self.skip:return
  if tag in ['p','div','li','h1','h2','h3','br','tr']:self.text.append('\n')
  if tag=='a':self.link=[dict(attrs).get('href',''),[]]
  if tag=='h1':self.h1=True
 def handle_endtag(self,tag):
  if tag in ['script','style']:self.skip=max(0,self.skip-1);return
  if self.skip:return
  if tag in ['p','div','li','h1','h2','h3','br','tr']:self.text.append('\n')
  if tag=='a' and self.link:self.links.append((self.link[0],''.join(self.link[1])));self.link=None
  if tag=='h1':self.h1=False
 def handle_data(self,value):
  if self.skip:return
  self.text.append(value)
  if self.link:self.link[1].append(value)
  if self.h1:self.title.append(value)
def heading_date(title,today):
 m=re.search(r'(?:ГПВ|погодинних відключень).*?на\s+(\d{1,2})\s+([а-яіїєґ]+)',title,re.I|re.S)
 if not m or m[2].lower() not in MONTHS:raise ValueError('Not a daily schedule title')
 for offset in [0,1,-1]:
  value=today+datetime.timedelta(days=offset)
  if value.day==int(m[1]) and value.month==MONTHS.index(m[2].lower())+1:return value
 raise ValueError('Title is for another day')
def clock(value):
 h,m=map(int,value.split(':'))
 if not(0<=h<=24 and 0<=m<60 and(h<24 or m==0)):raise ValueError('Invalid clock')
 return h*60+m
def parse(raw,today,url):
 d=Document();d.feed(raw.decode('utf-8'));title=''.join(d.title);date=heading_date(title,today);text=''.join(d.text)
 stamp=re.search(r'(\d{2})\.(\d{2})\.(\d{4})\s+(\d{2}):(\d{2})',text)
 if not stamp:raise ValueError('Publication timestamp missing')
 published=datetime.datetime(*map(int,[stamp[3],stamp[2],stamp[1],stamp[4],stamp[5]]))
 if not date-datetime.timedelta(days=2)<=published.date()<=date:raise ValueError('Publication date not bounded to target date')
 section=re.split(r'Години відсутності електропостачання\s*:',text,flags=re.I)[-1]
 if section==text:raise ValueError('Intervals section missing')
 section=re.split(r'Свою чергу|Також|Сторінка',section,flags=re.I)[0]
 section=re.sub(r'(\d{2})\s*:\s*(\d{2})',r'\1:\2',section)
 markers=list(re.finditer(r'(?<![\d.:])([1-6]\.[12])(?![\d.:])',section));names=[m[1] for m in markers]
 if not names or len(set(names))!=len(names):raise ValueError('Missing/duplicate queue names')
 partial=set(names)!=QUEUES
 if partial and not title.strip().lower().startswith('оновл'):raise ValueError('Incomplete full-day publication')
 schedules={}
 for i,m in enumerate(markers):
  value=section[m.end():markers[i+1].start() if i+1<len(markers) else len(section)]
  matches=list(re.finditer(r'((?:[01]\d|2[0-3]):[0-5]\d)\s*[-–—]\s*((?:[01]\d|2[0-3]):[0-5]\d|24:00)',value))
  remainder=value
  for item in reversed(matches):remainder=remainder[:item.start()]+remainder[item.end():]
  if re.search(r'\d',remainder) or not matches and not re.search(r'без відключень|не вимикається|відключення відсутні',value,re.I):raise ValueError('Unexplained interval contents')
  ranges=[(clock(x[1]),clock(x[2])) for x in matches]
  if any(b<=a for a,b in ranges) or any(ranges[j][0]<ranges[j-1][1] for j in range(1,len(ranges))):raise ValueError('Invalid interval order')
  schedules[m[1]]=ranges
 return {'title':title,'date':date.isoformat(),'publishedAtLocal':published.isoformat(),'partial':partial,'queues':schedules,'sourceUrl':url,'sha256':hashlib.sha256(raw).hexdigest()}
def fetch(url):
 u=urlsplit(url)
 if u.scheme!='https' or u.netloc!='www.cherkasyoblenergo.com':raise ValueError('Only the official source is allowed')
 with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'SvitloScheduleQA/1.0'}),timeout=30) as r:
  if r.url!=url:raise ValueError('Unexpected source redirect')
  raw=r.read(2_500_001)
 if len(raw)>2_500_000:raise ValueError('Source too large')
 return raw
def observe(directory,today=None):
 directory=pathlib.Path(directory);directory.mkdir(parents=True,exist_ok=True)
 today=today or datetime.datetime.now(zoneinfo.ZoneInfo('Europe/Kyiv')).date();raw=fetch(HOME);(directory/'home.html').write_bytes(raw);doc=Document();doc.feed(raw.decode('utf-8'));links=[]
 for href,label in doc.links:
  try:date=heading_date(label,today)
  except ValueError:continue
  url=urljoin(HOME,href)
  if date==today and urlsplit(url).netloc=='www.cherkasyoblenergo.com' and urlsplit(url).path.startswith('/media/') and url not in links:links.append(url)
 versions=[]
 for order,url in enumerate(links[:18]):
  raw=fetch(url);(directory/('article-'+str(order)+'.html')).write_bytes(raw);value=parse(raw,today,url);value['order']=order;versions.append(value)
 if not versions:raise ValueError('No current public publication')
 versions.sort(key=lambda x:(x['publishedAtLocal'],-x['order']));first=next((i for i,v in enumerate(versions) if not v['partial']),None)
 if first is None:raise ValueError('No complete base publication')
 queues=dict(versions[first]['queues'])
 for version in versions[first+1:]:
  instant=datetime.datetime.fromisoformat(version['publishedAtLocal']);cutoff=instant.hour*60+instant.minute if instant.date()==today else 0
  for q,current in version['queues'].items():
   ranges=sorted([(a,min(b,cutoff)) for a,b in queues[q]]+[(max(a,cutoff),b) for a,b in current]);merged=[]
   for a,b in ranges:
    if b<=a:continue
    if merged and a<=merged[-1][1]:merged[-1][1]=max(b,merged[-1][1])
    else:merged.append([a,b])
   queues[q]=merged
 report={'observedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'date':today.isoformat(),'homeSha256':hashlib.sha256((directory/'home.html').read_bytes()).hexdigest(),'versions':versions,'queues':queues,'scope':'Independent official public text observation; no application queue lookup is inferred.'}
 (directory/'observation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');return report
