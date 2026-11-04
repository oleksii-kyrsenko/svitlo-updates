"""Current official city GPV documents. No subscriber/account requests.

The Rivne route preserves literal source rows and explicit parity only. It
normalizes punctuation after an explicitly written street type, not road names.
"""
import argparse, gzip, hashlib, html, io, json, re, time, urllib.parse, urllib.request
from pathlib import Path
import pdfplumber
from official_rosters import (Links, clean, explicit_houses, uncertain_ranges,
                              record, without_conflicts, _TYPE, _LANDMARK)

INDEX='https://www.roe.vsei.ua/disconnections'

def canonical_street(value):
    # A dot terminates an abbreviation even when the PDF omits its space.
    return re.sub(r'^(вул\.|пров\.|просп\.|пр\.|пл\.|бул\.)\s*(?=\S)',r'\1 ',clean(value),flags=re.I)

def city_link(body, parent=INDEX):
    p=Links();p.feed(body);links=[]
    for href,label in p.links:
        if not re.search(r'Дізнатися\s+чергу\s+відключень\s+у\s+м\.\s*Рівне',label,re.I):continue
        url=urllib.parse.urljoin(parent,href);u=urllib.parse.urlsplit(url)
        if u.scheme!='https' or u.netloc!='www.roe.vsei.ua' or u.query or u.fragment or not re.fullmatch(r'/wp-content/uploads/\d{4}/\d{2}/GPV_cherga_misto_Rivne[-\w]*\.pdf',u.path,re.I):raise ValueError('unverified_city_attachment')
        links.append(url)
    links=list(dict.fromkeys(links))
    if len(links)!=1:raise ValueError('current_city_attachment_not_unique')
    return links[0]

def decode_tables(tables,url,checked_at,geo):
    queues=set();raw_rows=[];header=False
    for table in tables:
        for cells in table:
            if len(cells)!=3:continue
            _,raw,q=[clean(v) for v in cells]
            header|=bool(re.search(r'Назви вулиць.*м\.\s*Рівне',raw,re.I) and re.search('підчерга',q,re.I))
            q=q.replace(',','.')
            if not re.fullmatch(r'[1-6]\.[12]',q):continue
            queues.add(q)
            text=re.sub(r'(?<!^)(?<![А-Яа-яІіЇїЄєҐґ])(?='+_TYPE+r'\s*)',';',raw,flags=re.I)
            for chunk in text.split(';'):
                for piece in re.split(r',\s*(?=[А-Яа-яІіЇїЄєҐґA-Za-z][^,;]*?\s+\d)',chunk.strip(' ,.;')):
                    if re.search(r'частков|приватн|промзон|біля|перехрест|\+|селищ',piece,re.I):continue
                    match=re.fullmatch(r'(.+?[А-Яа-яІіЇїЄєҐґA-Za-z\'])\s*[, ]\s*(\d.*)',piece)
                    if not match:continue
                    street,numbers=match[1].strip(' ,.'),match[2]
                    if _LANDMARK.search(street):continue
                    numbers=re.split(r',\s*(?=[^\d\s])',numbers,maxsplit=1)[0]
                    if not re.match(r'^'+_TYPE+r'\s*',street,re.I):street='вул. '+street
                    street=canonical_street(street);houses=explicit_houses(numbers,expand_ranges=True)
                    row=record('rivne','UA-56',geo['settlement'],geo['community'],street,houses,q,url,f'м.Рівне; підчерга {q}; рядок офіційної таблиці: {raw}',checked_at)
                    ranges=[]
                    for part in re.split(r'[,;]',numbers):
                        # Explicit parity is already an exact finite set. It
                        # must not veto the other parity in a different queue.
                        qualified=re.fullmatch(r'\s*\d{1,4}\s*[-–—]\s*\d{1,4}\s*\((?:непарні|парні|усі|всі)\)\s*',part,re.I)
                        if not(qualified and explicit_houses(part,expand_ranges=True)):ranges.extend(uncertain_ranges(part))
                    if row:
                        if ranges:row['_uncertainRanges']=ranges
                        raw_rows.append(row)
                    elif ranges:raw_rows.append({'settlement':geo['settlement'],'street':street,'queue':q,'houses':[],'_uncertainRanges':ranges})
    if not header or queues!={f'{a}.{b}' for a in range(1,7) for b in (1,2)}:raise ValueError('incomplete_city_queue_document')
    observed={}
    for row in raw_rows:
        for house in row['houses']:
            key=(row['street'],house);observed[key]={'regionId':'UA-56','settlement':geo['settlement'],'community':geo['community'],'street':row['street'],'house':house,'checkedAt':checked_at,'expiresAt':checked_at+86400000}
    rows=without_conflicts(raw_rows);merged={}
    # A PDF row can mention one road twice. Its provenance-derived ID is
    # shared, so union its literal houses instead of dropping an earlier part.
    for row in rows:
        if row['id'] not in merged:merged[row['id']]=row
        else:merged[row['id']]['houses']=list(dict.fromkeys(merged[row['id']]['houses']+row['houses']))
    return list(merged.values()),list(observed.values()),sorted(queues)

class HTTP:
    def __init__(self,limit,evidence):self.limit=limit;self.trace=[];self.evidence=Path(evidence) if evidence else None
    def get(self,url):
        if len(self.trace)>=self.limit:raise ValueError('request_budget')
        from request_budget import throttle
        throttle(url);req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (Koly Svitlo public source collector)','Referer':INDEX,'Accept-Language':'uk'})
        at=int(time.time()*1000)
        with urllib.request.urlopen(req,timeout=25) as response:
            raw=response.read(6000001)
            if len(raw)>6000000:raise ValueError('source_response_too_large')
            if urllib.parse.urlsplit(response.geturl()).netloc!='www.roe.vsei.ua':raise ValueError('source_redirect_outside_official_host')
            event={'url':url,'responseUrl':response.geturl(),'checkedAt':at,'httpStatus':response.status,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
        if self.evidence:
            self.evidence.mkdir(parents=True,exist_ok=True);name=event['sha256']+'.bin';(self.evidence/name).write_bytes(raw);event['originalFile']=name
        self.trace.append(event)
        decoded=gzip.decompress(raw) if raw.startswith(b'\x1f\x8b') else raw
        if len(decoded)>6000000:raise ValueError('decoded_source_response_too_large')
        return decoded,at

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--operator',choices=['rivne'],required=True);p.add_argument('--target-city',default='Рівне');p.add_argument('--full-city',action='store_true');p.add_argument('--output',required=True);p.add_argument('--state');p.add_argument('--request-limit',type=int,default=4);p.add_argument('--evidence-directory');a=p.parse_args()
    if not 2<=a.request_limit<=32:raise ValueError('invalid_request_budget')
    cities=json.loads(Path(__file__).with_name('capital-geography.json').read_text())['cities'];matches=[c for c in cities if c['regionId']=='UA-56' and c['settlement']==a.target_city]
    if len(matches)!=1 or not matches[0].get('community'):raise ValueError('verified_city_context_required')
    geo=matches[0];http=HTTP(a.request_limit,a.evidence_directory);rows=[];obs=[];queues=[];errors=[]
    try:
        parent,t0=http.get(INDEX);url=city_link(parent.decode('utf8'));raw,t1=http.get(url)
        if not raw.startswith(b'%PDF-'):raise ValueError('official_attachment_is_not_pdf')
        with pdfplumber.open(io.BytesIO(raw)) as pdf:
            if not 1<=len(pdf.pages)<=20:raise ValueError('unexpected_city_document_length')
            tables=[t for page in pdf.pages for t in page.extract_tables()]
        rows,obs,queues=decode_tables(tables,url,min(t0,t1),geo)
    except Exception as error:errors.append({'error':type(error).__name__,'reason':str(error)[:160],'httpStatus':getattr(error,'code',None)})
    out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True);now=int(time.time()*1000)
    report={'operatorId':'rivne','generatedAt':now,'requests':http.trace,'errors':errors,'records':len(rows),'positiveHouseFacts':sum(len(r['houses']) for r in rows),'observedHouses':len(obs),'queuesRead':queues,'cityCrawl':{'targetCity':geo['settlement'],'mode':'current-active-official-city-GPV-document','status':'complete-document' if not errors else 'blocked','dictionaryComplete':False},'method':'Source-derived literal and explicitly qualified house lists; not Android UI coverage. Street-type punctuation only is normalized. Partial/bare streets and unqualified ranges do not create houses.'}
    Path(str(out)+'.report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    if errors or not rows:raise SystemExit(2)
    packet={'schemaVersion':1,'operatorId':'rivne','generatedAt':now,'expiresAt':max(r['expiresAt'] for r in rows),'records':rows,'observedHouses':obs,'completedStreetIds':[]};out.write_text(json.dumps(packet,ensure_ascii=False,separators=(',',':'))+'\n');print(json.dumps({k:report[k] for k in ['records','positiveHouseFacts','observedHouses','errors']},ensure_ascii=False))

if __name__=='__main__':main()
