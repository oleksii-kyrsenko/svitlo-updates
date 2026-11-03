"""Current official Prykarpattia GPV house tables; no subscriber queries.

Reads all twelve currently linked GPV PDFs before releasing literal city facts.
GAВ tables, expired periods, ranges and conflicting connections never assign queues.
"""
import argparse,datetime,gzip,hashlib,html,io,json,re,time,unicodedata,urllib.parse,urllib.request
from pathlib import Path
import pdfplumber

INDEX='https://oe.if.ua/uk/sections/5e9f1c5fdb9c42704449b999'
MAX=16000000
DAY=86400000
def clean(value):return re.sub(r'\s+',' ',str(value or '')).strip()
def key(value):return clean(unicodedata.normalize('NFKC',str(value))).casefold().replace('’',"'").replace('ʼ',"'").replace('–','-')
def digest(data):return hashlib.sha256(data).hexdigest()
def house(value):
 value=clean(value)
 return value if re.fullmatch(r'\d{1,4}(?:[ -]?[А-Яа-яІіЇїЄєҐґA-Za-z])?(?:/\d{1,4}(?:[ -]?[А-Яа-яІіЇїЄєҐґA-Za-z])?)?',value) else None
def house_key(value):
 value=key(value).replace(' ','').translate(str.maketrans({'a':'а','c':'с','e':'е','o':'о','p':'р','x':'х'}))
 return re.sub(r'(?<=\d)-(?=[а-яіїєґ])','',value)
def decoded(raw):
 if raw.startswith(b'\x1f\x8b'):
  with gzip.GzipFile(fileobj=io.BytesIO(raw)) as f:value=f.read(MAX+1)
 else:value=raw
 if len(value)>MAX:raise ValueError('decompressed_source_limit')
 return value
def utc(value):return int(datetime.datetime.strptime(value,'%d.%m.%Y').replace(tzinfo=datetime.timezone.utc).timestamp()*1000)
def documents(text,now):
 # Comments cannot make archived documents current.
 text=re.sub(r'<!--.*?-->','',text,flags=re.S)
 heading=re.search(r'<h3\b[^>]*>\s*Графіки погодинних вимкнень\s*</h3>',text,re.I)
 if not heading:raise ValueError('current_GPV_section_missing')
 section=text[heading.end():];end=section.find('</ul>')
 if end<0:raise ValueError('current_document_list_missing')
 section=section[:end]
 plain=clean(html.unescape(re.sub('<[^>]*>',' ',section)))
 date=re.search(r'Графіки погодинних вимкнень\s+з\s+(\d{2}\.\d{2}\.\d{4})\s+(?:до|по)\s+(\d{2}\.\d{2}\.\d{4})',plain,re.I)
 if not date:raise ValueError('current_GPV_period_missing')
 start,until=utc(date[1]),utc(date[2])
 if not start<=now<until:raise ValueError('GPV_period_not_current')
 docs=[]
 for m in re.finditer(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',section,re.I|re.S):
  url=urllib.parse.urljoin(INDEX,html.unescape(m[1]));u=urllib.parse.urlsplit(url)
  name=re.search(r'<div\b[^>]*class=["\']name["\'][^>]*>\s*([1-6]\.[12])\s*</div>',m[2],re.I|re.S)
  if not name:continue
  if u.scheme!='https' or u.hostname not in ('oe.if.ua','www.oe.if.ua') or u.query or u.fragment or u.username or not re.fullmatch(r'/uploads/question_document/document/[a-f0-9]{24}/'+re.escape(name[1])+r'\.pdf',u.path):raise ValueError('untrusted_current_document')
  docs.append({'queue':name[1],'url':url,'effectiveFrom':start,'effectiveUntil':until})
 expected={f'{a}.{b}' for a in range(1,7) for b in (1,2)}
 if len(docs)!=12 or {d['queue'] for d in docs}!=expected or len({d['url'] for d in docs})!=12:raise ValueError('incomplete_current_queue_documents')
 return docs

class HTTP:
 def __init__(self,limit=16,evidence=None):self.limit=limit;self.calls=0;self.trace=[];self.evidence=Path(evidence) if evidence else None
 def get(self,url):
  if self.calls>=self.limit:raise ValueError('request_budget')
  from request_budget import throttle
  throttle(url);self.calls+=1;at=int(time.time()*1000)
  with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (KolySvitlo public official GPV collector)','Accept-Encoding':'identity'}),timeout=40) as r:
   raw=r.read(MAX+1);final=r.geturl();status=r.status;encoding=r.headers.get('Content-Encoding')
  if len(raw)>MAX:raise ValueError('source_limit')
  if urllib.parse.urlsplit(final).hostname not in ('oe.if.ua','www.oe.if.ua'):raise ValueError('source_redirect_outside_operator')
  body=decoded(raw);event={'url':url,'finalUrl':final,'httpStatus':status,'checkedAt':at,'rawSha256':digest(raw),'rawBytes':len(raw),'decodedSha256':digest(body),'decodedBytes':len(body),'contentEncoding':encoding}
  if self.evidence:
   folder=self.evidence/'raw';folder.mkdir(parents=True,exist_ok=True);(folder/(digest(raw)+'.bin')).write_bytes(raw)
  self.trace.append(event);return body,at

def parse_tables(tables,document,target):
 claims=[]
 for table in tables:
  for cells in table:
   if len(cells)!=6:continue
   q1,q2,district,city,street,numbers=[clean(x) for x in cells]
   if re.fullmatch('[1-6]',q1) and re.fullmatch('[12]',q2) and q1+'.'+q2!=document['queue']:raise ValueError('document_queue_disagreement')
   if key(city)!=key(target):continue
   if q1+'.'+q2!=document['queue'] or key(district)!='івано-франківський' or not street:raise ValueError('city_row_identity_not_verified')
   literal=[];unknown=[];ranges=[]
   for token in re.split('[,;]',numbers):
    token=clean(token);h=house(token)
    if h:literal.append(h)
    elif (match:=re.fullmatch(r'(\d{1,4})\s*[-–—]\s*(\d{1,4})',token)):
     lo,hi=map(int,match.groups())
     if lo>hi:unknown.append(str(lo))
     else:ranges.append((lo,hi))
    elif (match:=re.match(r'^(\d{1,4})(?=\s|[-/А-Яа-яІіЇїЄєҐґA-Za-z]|$)',token)):unknown.append(match[1])
   claims.append({'street':street,'houses':literal,'unknownHouses':unknown,'ranges':ranges,'queue':document['queue'],'sourceUrl':document['url'],'rawHouseCell':numbers})
 return claims

def read_pdf(raw,document,target):
 if not raw.startswith(b'%PDF'):raise ValueError('document_not_pdf')
 claims=[];scanned=0
 with pdfplumber.open(io.BytesIO(raw)) as pdf:
  if not pdf.pages or len(pdf.pages)>300:raise ValueError('document_page_bounds')
  header=pdf.pages[0].extract_text() or ''
  if not all(word in header for word in ('Черга','Підчерга','Населений пункт','Вулиця','Будинки')):raise ValueError('official_document_table_changed')
  for i,page in enumerate(pdf.pages):
   text=page.extract_text() or ''
   # Fast prefilter, not address extraction: exact city identity is rechecked in cells.
   if re.search(r'(?<![\w-])'+re.escape(target)+r'(?![\w-])',text):
    parsed=parse_tables(page.extract_tables(),document,target)
    for c in parsed:c['page']=i+1
    claims.extend(parsed);scanned+=1
   page.close()
 return claims,{'pages':len(pdf.pages),'candidateCityPages':scanned,'cityRows':len(claims)}

def consolidate(claims,geo,at,until):
 facts={};by_street={}
 for c in claims:
  by_street.setdefault(key(c['street']),[]).append(c)
  for h in c['houses']:facts.setdefault((key(c['street']),house_key(h)),[]).append((h,c))
 groups={};obs=[];abstained=0;expires=min(at+DAY,until)
 for (street_key,hkey),items in sorted(facts.items()):
  h=items[0][0];c=items[0][1];qs={v['queue'] for _,v in items};number=int(re.match(r'\d+',h)[0])
  uncertain=any(house_key(v)==hkey for v in [x for row in by_street[street_key] for x in row['unknownHouses']])
  uncertain=uncertain or any(lo<=number<=hi and row['queue'] not in qs for row in by_street[street_key] for lo,hi in row['ranges'])
  obs.append({'regionId':geo['regionId'],'settlement':geo['settlement'],'community':geo['community'],'street':c['street'],'house':h,'checkedAt':at,'expiresAt':expires})
  if uncertain or len(qs)!=1:abstained+=1;continue
  groups.setdefault((c['street'],c['queue'],c['sourceUrl']),[]).append(h)
 records=[]
 for (street,q,url),houses in sorted(groups.items()):
  for start in range(0,len(houses),60):
   chunk=houses[start:start+60];quote=f"{geo['settlement']}; {street}; будинки {', '.join(chunk)}; черга ГПВ {q}. Офіційна адресна таблиця."
   records.append({'id':'western-'+digest(json.dumps([street,q,chunk],ensure_ascii=False).encode())[:24],'official':True,'regionId':geo['regionId'],'settlement':geo['settlement'],'community':geo['community'],'street':street,'scope':'house','houses':chunk,'queue':q,'sourceUrl':url,'quote':quote,'checkedAt':at,'expiresAt':expires})
 return records,obs,abstained

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--operator',choices=['prykarpattia'],required=True);p.add_argument('--target-city',required=True);p.add_argument('--output',required=True);p.add_argument('--state');p.add_argument('--full-city',action='store_true');p.add_argument('--request-limit',type=int,default=16);p.add_argument('--evidence-directory');p.add_argument('--budget',type=int);p.add_argument('--street-limit',type=int);p.add_argument('--city-limit',type=int);a=p.parse_args()
 if not 1<=a.request_limit<=2000:raise ValueError('invalid_request_budget')
 geo=[g for g in json.loads(Path(__file__).with_name('capital-geography.json').read_text())['cities'] if g['regionId']=='UA-26' and key(g['settlement'])==key(a.target_city)]
 if len(geo)!=1 or not geo[0].get('community'):raise ValueError('verified_city_context_required')
 geo=geo[0];output=Path(a.output);output.parent.mkdir(parents=True,exist_ok=True);http=HTTP(a.request_limit,a.evidence_directory);claims=[];sources=[];errors=[];rows=[];observations=[];abstained=0;complete=False
 try:
  raw,at=http.get(INDEX);docs=documents(raw.decode('utf-8'),at);times=[at]
  for doc in docs:
   raw,checked=http.get(doc['url']);times.append(checked);items,meta=read_pdf(raw,doc,geo['settlement']);claims.extend(items);sources.append({**doc,**meta,'sha256':digest(raw),'checkedAt':checked,'claims':items})
  observed_at=min(times);rows,observations,abstained=consolidate(claims,geo,observed_at,min(d['effectiveUntil'] for d in docs));complete=True
 except Exception as e:errors.append({'error':type(e).__name__,'reason':str(e)[:160],'httpStatus':getattr(e,'code',None)})
 now=int(time.time()*1000);report={'operatorId':a.operator,'checkedAt':now,'records':len(rows),'positiveHouses':sum(len(r['houses']) for r in rows),'observedHouses':len(observations),'abstained':abstained,'requests':http.trace,'sources':sources,'errors':errors,'cityCrawl':{'targetCity':geo['settlement'],'status':'complete' if complete else 'blocked','mode':'current-official-GPV-documents','allCurrentQueueDocumentsRead':complete,'dictionaryComplete':False},'method':'Literal source-derived house assignments, not independent Android UI coverage. No numeric range expansion.'}
 Path(str(output)+'.report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 if a.evidence_directory:(Path(a.evidence_directory)/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 if complete and observations:
  bundle={'schemaVersion':1,'operatorId':a.operator,'generatedAt':now,'expiresAt':max(o['expiresAt'] for o in observations),'records':rows,'observedHouses':observations,'completedStreetIds':[]};output.write_text(json.dumps(bundle,ensure_ascii=False,separators=(',',':'))+'\n')
  if a.state:Path(a.state).write_text(json.dumps({'schemaVersion':1,'lastCompleteAt':min(times),'currentDocumentHashes':[s['sha256'] for s in sources]},indent=2)+'\n')
 print(json.dumps({k:report[k] for k in ('operatorId','records','positiveHouses','observedHouses','abstained','errors')},ensure_ascii=False))
 if not complete or not observations:raise SystemExit(2)
if __name__=='__main__':main()
