"""Public document collection for remaining networks. No private application code.
Only explicit complete-locality rows and literal house lists become records.
"""
import argparse,concurrent.futures,hashlib,html,io,json,re,time,urllib.request,urllib.error,urllib.parse
from pathlib import Path
from html.parser import HTMLParser
IDS='poltava rivne zaporizhzhia kharkiv kherson chernihiv atomservice naftogaz-teplo ukrzaliznytsia luhansk regional-networks'.split()
MAX=16000000

def fetch(url):
 from request_budget import throttle
 throttle(url)
 url=urllib.parse.quote(url,safe=":/?=&%#")
 with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (KolySvitlo public data collector)','Accept-Language':'uk'}),timeout=25) as r:
  data=r.read(MAX+1)
  if len(data)>MAX:raise ValueError('response_too_large')
  return data,r.geturl()
def clean(s):return re.sub(r'\s+',' ',html.unescape(re.sub('<[^>]+>',' ',s))).strip()
def identity(s):return hashlib.sha256(s.encode()).hexdigest()[:24]
def base_record(operator,region,city,community,queue,url,quote,now):
 return {'id':identity('|'.join([operator,city,community,quote,queue])),'regionId':region,'settlement':city,'community':community,'queue':queue,'sourceUrl':url,'quote':quote[:2500],'quoteType':'structured-official-fields','checkedAt':now,'expiresAt':now+86400000,'official':True}

def rivne_records(tables,url,now):
 out=[];claims={}
 for table in tables:
  for cells in table:
   if len(cells)!=4:continue
   community,localities,details,queue=[clean(x or '') for x in cells]
   if not re.fullmatch(r'[1-6]\.[12]',queue) or not community or re.search(r'\d|громади|Графік',community):continue
   for mention in re.finditer(r'(?:^|[,;])\s*(?:м\.|с\.|смт\.?|с-ще)\s*([^(),;]+)',localities,re.I):
    claims.setdefault((community,mention[1].strip()),set()).add(queue)
   # Only the source's explicit '(повністю)' permits settlement-wide coverage.
   for m in re.finditer(r'(?:^|[,;])\s*(?:м\.|с\.|смт\.?|с-ще)\s*([\w’ʼ\'-]+(?:\s+[\w’ʼ\'-]+)*)\s*\(повністю\)',localities,re.I):
    city=m[1].strip();quote=f'весь населений пункт {city} (повністю); громада {community}; черга {queue}. Поля офіційної таблиці: {localities}'
    r=base_record('rivne','UA-56',city,community,queue,url,quote,now);r['scope']='settlement';out.append(r)
 return [r for r in out if len(claims.get((r['community'],r['settlement']),set()))==1]

class AtomTables(HTMLParser):
 def __init__(self):super().__init__(convert_charrefs=True);self.heading=False;self.heading_text='';self.queue=None;self.cell=False;self.text='';self.cells=[];self.rows=[]
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if tag=='div' and a.get('class')=='title_p':self.heading=True;self.heading_text=''
  if tag=='tr':self.cells=[]
  if tag=='td':self.cell=True;self.text=''
  if tag=='br' and self.cell:self.text+='\n'
 def handle_data(self,d):
  if self.heading:self.heading_text+=d
  if self.cell:self.text+=d
 def handle_endtag(self,tag):
  if tag=='div' and self.heading:
   m=re.search(r'Підчерга\s*([1-6])[-–]([ІI]{1,2})\b',self.heading_text)
   self.queue=f'{m[1]}.{len(m[2])}' if m else None;self.heading=False
  if tag=='td' and self.cell:self.cells.append(self.text.strip());self.cell=False
  if tag=='tr' and len(self.cells)==5 and self.queue:self.rows.append((self.queue,self.cells))

def atom_house_rows(text,url,now,resolve):
 p=AtomTables();p.feed(text);out=[];contexts={}
 for queue,cells in p.rows:
  m=re.fullmatch(r'м\.\s*(.+)',clean(cells[0]));city=m[1].strip() if m else None
  if not city:continue
  if city not in contexts:contexts[city]=resolve(city,'UA-48',url)
  community=contexts[city]
  if not community:continue
  for line in cells[-1].splitlines():
   # Numeric ranges, houses partly covered, landmarks and named businesses abstain.
   m=re.fullmatch(r'\s*((?:вул\.|пр-т|б-р|пров\.)\s*[^\d;:]+?)\s+([\d\wА-Яа-яІіЇїЄєҐґ,\s-]+)\s*;?\s*',line)
   if not m:continue
   street=m[1].strip();houses=[x.strip() for x in m[2].split(',')]
   if not houses or any(not re.fullmatch(r'\d+(?:[- ]?[А-Яа-яІіЇїЄєҐґA-Za-z])?',h) for h in houses):continue
   quote=f'{city}, {street}, будинки {", ".join(houses)}; черга {queue}'
   r=base_record('atomservice','UA-48',city,community,queue,url,quote,now);r.update(scope='house',street=street,houses=houses);out.append(r)
 # More than one public connection at an exact house cannot become a chosen queue.
 claims={}
 for r in out:
  for h in r['houses']:claims.setdefault((r['settlement'],r['street'],h),set()).add(r['queue'])
 for r in out:r['houses']=[h for h in r['houses'] if len(claims[(r['settlement'],r['street'],h)])==1]
 return [r for r in out if r['houses']]

def resolve_community(city,region,url):
 try:
  from geography import resolve
  result=resolve({'settlement':city,'regionId':region,'sourceUrl':url})
  return result.get('community') if result.get('status')=='resolved' else None
 except (ImportError,AttributeError):return None

def main():
 a=argparse.ArgumentParser();a.add_argument('--operator',choices=IDS,required=True);a.add_argument('--output',required=True);a.add_argument('--state');a.add_argument('--budget',type=int,default=20);args=a.parse_args()
 cfg=json.loads(Path('coverage/sources.json').read_text());source=next(o for o in cfg['operators'] if o['id']==args.operator);now=int(time.time()*1000)
 report={'operatorId':args.operator,'checkedAt':now,'records':0,'sourceChecks':[],'caseChecks':[],'method':'source-derived-roster-check-not-independent-address-audit'};rows=[]
 try:
  data,url=fetch(source['sourceUrl']);text=data.decode('utf8','replace');report['sourceChecks'].append({'url':url,'status':'available','bytes':len(data)})
  if args.operator=='rivne':
   from official_rosters import rivne_city_records
   links=[urllib.parse.urljoin(url,html.unescape(u)) for u in re.findall(r'href=["\']([^"\']+\.pdf)',text,re.I) if re.search(r'GPV_cherga_(?:Rivnenska_oblast|misto_Rivne)',u,re.I)]
   links=list(dict.fromkeys(links));community=resolve_community('Рівне','UA-56',url)
   import pdfplumber
   for doc in links[:2]:
    data,final=fetch(doc)
    with pdfplumber.open(io.BytesIO(data)) as pdf:tables=[t for page in pdf.pages for t in page.extract_tables()]
    city_document=bool(re.search(r'misto_Rivne',doc,re.I))
    parsed=rivne_city_records(tables,final,now,community) if city_document else rivne_records(tables,final,now)
    rows.extend(parsed);report['sourceChecks'].append({'url':final,'status':'parsed-official-pdf','tables':len(tables),'kind':'city-addresses' if city_document else 'oblast-localities','records':len(parsed),'sha256':hashlib.sha256(data).hexdigest()})
   report['collectionScope']={'settlement':'Рівне','sourceTraversal':'complete-linked-documents','addressCoverage':'partial-explicit-house-lists','omissions':['unqualified-ranges','bare-street-or-partial-area-descriptions','conflicting-connections']}
  elif args.operator=='zaporizhzhia':
   from official_rosters import Links,zaporizhzhia_roster_links,google_sheet_pages,zaporizhzhia_sheet_records,without_conflicts
   p=Links();p.feed(text)
   article=next((urllib.parse.urljoin(url,u) for u,label in p.links if re.search(r'Перелік адрес',label,re.I) and re.search(r'по\s*м\.\s*Запоріжжя',label,re.I)),None)
   if not article:raise ValueError('official_city_roster_link_missing')
   data,article=fetch(article);rosters=zaporizhzhia_roster_links(data.decode('utf8','replace'));community=resolve_community('Запоріжжя','UA-23',article)
   if not rosters:raise ValueError('official_city_queue_links_missing')
   if not community:raise ValueError('verified_community_missing')
   completed=[];failed=[]
   for roster in rosters:
    try:
     wrapper,wrapper_url=fetch(roster['url']);pages=google_sheet_pages(wrapper.decode('utf8','replace'),wrapper_url)
     if not pages:raise ValueError('public_sheet_pages_missing')
     sheet_rows=[]
     for sheet in pages[:3]:
      data,final=fetch(sheet);parsed=zaporizhzhia_sheet_records(data.decode('utf8','replace'),roster['queue'],final,now,community);sheet_rows.extend(parsed)
      report['sourceChecks'].append({'url':final,'status':'parsed-official-linked-sheet','queue':roster['queue'],'records':len(parsed),'sha256':hashlib.sha256(data).hexdigest()})
     if not sheet_rows:raise ValueError('no_literal_house_assignments')
     rows.extend(sheet_rows);completed.append(roster['queue'])
    except Exception as e:failed.append({'queue':roster['queue'],'error':type(e).__name__,'httpStatus':getattr(e,'code',None)})
   rows=without_conflicts(rows)
   report['collectionScope']={'settlement':'Запоріжжя','sourceTraversal':'complete-linked-documents' if not failed else 'partial-linked-documents','completedQueues':completed,'failedQueues':failed,'addressCoverage':'partial-explicit-house-lists','omissions':['unqualified-ranges','conflicting-connections']}
   # Missing one queue can hide conflicting connections. Do not promote the
   # remaining lists as a safe city snapshot until all linked lists were read.
   if failed:rows=[];report['constraint']='incomplete-official-city-roster-read'
  elif args.operator=='atomservice':rows=atom_house_rows(text,url,now,resolve_community)
  else:
   # Discovery preserves links as leads, never treats them as confirmed queues.
   leads=[urllib.parse.urljoin(url,html.unescape(u)) for u in re.findall(r'href=["\']([^"\']+)',text,re.I) if re.search(r'\.pdf|\.xlsx|t\.me/|google.com|відключ|shutdown|gaoinfo',u,re.I)]
   report['leads']=[{'url':u,'status':'needs_source_review'} for u in sorted(set(leads))[:30]]
   report['constraint']='registry-identity-only-no-address-source' if args.operator in ['luhansk','regional-networks'] else 'address-protocol-or-geographic-context-not-yet-verified'
 except Exception as e:report.update(constraint='source-protected' if isinstance(e,urllib.error.HTTPError) and e.code in (403,429) else 'collection-unavailable',error=type(e).__name__,httpStatus=getattr(e,'code',None))
 # Conflicting locality-wide records are omitted even if a smaller subset appears usable.
 claims={}
 for r in rows:
  if r['scope']=='settlement':claims.setdefault((r['community'],r['settlement']),set()).add(r['queue'])
 rows=[r for r in rows if r['scope']!='settlement' or len(claims[(r['community'],r['settlement'])])==1]
 rows=list({r['id']:r for r in rows}.values());report['records']=len(rows)
 report['caseChecks']=[{'settlement':r['settlement'],'community':r['community'],'scope':r['scope'],'street':r.get('street'),'house':r.get('houses',[None])[0],'queue':r['queue'],'sourceUrl':r['sourceUrl'],'check':'explicit-source-scope-and-no-conflicting-queue'} for r in rows[:20]]
 if not rows:report.setdefault('constraint','no-unambiguous-roster-with-verified-community')
 path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);Path(args.output+'.report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 if rows:path.write_text(json.dumps({'schemaVersion':1,'operatorId':args.operator,'generatedAt':now,'expiresAt':now+86400000,'records':rows,'completeSnapshot':args.operator not in ('rivne','zaporizhzhia')},ensure_ascii=False,separators=(',',':'))+'\n')
 print(json.dumps({'operatorId':args.operator,'records':len(rows),'constraint':report.get('constraint')}))
 if not rows:raise SystemExit(2)
if __name__=='__main__':main()
