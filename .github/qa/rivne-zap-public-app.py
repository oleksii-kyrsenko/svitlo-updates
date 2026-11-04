"""Read the operator-linked anonymous Zaporizhzhia Apps Script dictionary.

This is source-only evidence, not Android coverage and not a signed publication.
No address, account or EIC is submitted. The official page itself calls getData.
"""
import argparse, hashlib, json, pathlib, re, time, urllib.parse
from html.parser import HTMLParser
from playwright.sync_api import sync_playwright

INDEX='https://www.zoe.com.ua/outage/'
MAX_BYTES=10000000
def sha(raw):return hashlib.sha256(raw).hexdigest()
class Links(HTMLParser):
 def __init__(self):super().__init__(convert_charrefs=True);self.href=None;self.text='';self.links=[]
 def handle_starttag(self,tag,attrs):
  if tag=='a':self.href=dict(attrs).get('href');self.text=''
 def handle_data(self,data):
  if self.href is not None:self.text+=data
 def handle_endtag(self,tag):
  if tag=='a' and self.href is not None:self.links.append({'url':self.href,'label':self.text.strip()});self.href=None
def app_link(body,expected):
 p=Links();p.feed(body);links=[v for v in p.links if re.search(r'Дізнатися\s+свою\s+чергу.*м\.\s*Запоріжжя',v['label'],re.I) and re.fullmatch(r'https://script\.google\.com/macros/s/[-\w]+/exec',v['url'])]
 if len({v['url'] for v in links})!=1 or links[0]['url']!=expected:raise ValueError('official_public_app_resource_changed_review_required')
 return links[0]
def authority_snapshot(raw,meta,expected,now):
 at=meta.get('checkedAt');expires=meta.get('expiresAt')
 if meta.get('sourceUrl')!=INDEX or not isinstance(at,int) or not isinstance(expires,int) or not 0<at<=now<expires or expires!=at+86400000 or len(raw)>2000000 or sha(raw)!=meta.get('sha256'):raise ValueError('invalid_or_expired_reviewed_official_authority')
 return app_link(raw.decode('utf8'),expected)
def allowed(url):
 u=urllib.parse.urlsplit(url);h=u.hostname or ''
 return u.scheme=='https' and not u.username and not u.password and (h in ['www.zoe.com.ua','script.google.com','www.gstatic.com','ssl.gstatic.com','fonts.googleapis.com','fonts.gstatic.com'] or h.endswith('.googleusercontent.com'))
def project(data):
 if not isinstance(data,list) or not 1<=len(data)<=100000:raise ValueError('unexpected_public_dictionary_shape')
 rows=[];headers=0
 for r in data:
  if not isinstance(r,list) or len(r)<5:raise ValueError('unexpected_public_dictionary_row')
  street,house,gpv=[str(v or '').strip() for v in r[:3]]
  if not house and not street:continue
  if re.search('будин|будів',house,re.I) and re.search('вулиц',street,re.I):headers+=1;continue
  if len(street)>250 or len(house)>50 or len(gpv)>100 or re.search(r'\d{9,}|\b[0-9A-Z]{16}\b',street+' '+house+' '+gpv,re.I):raise ValueError('unexpected_non_address_public_field')
  # GPV is column2, ZOVA/partial exemptions column3; GAV column4 is NEVER
  # substituted. Exemption text and all other fields are not persisted.
  rows.append([street,house,gpv,bool(str(r[3] or '').strip())])
 encoded=json.dumps(rows,ensure_ascii=False,separators=(',',':')).encode()
 if len(encoded)>MAX_BYTES:raise ValueError('public_dictionary_projection_too_large')
 return rows,headers

def main():
 p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--request',required=True);a=p.parse_args();out=pathlib.Path(a.out);out.mkdir(parents=True,exist_ok=True)
 request=json.loads(pathlib.Path(a.request).read_text());trace=[];report={'schemaVersion':1,'method':'actual ordinary Chromium; current operator-linked anonymous Apps Script frontend getData on page load; no account/EIC/address input','coverageMeasured':False,'sourceUrl':INDEX,'checkedAt':int(time.time()*1000),'recordClaims':0,'requests':trace};start=time.monotonic()
 try:
  with sync_playwright() as api:
   browser=api.chromium.launch(headless=True);context=browser.new_context(locale='uk-UA');page=context.new_page();request_count=[0]
   def route(r):
    if not allowed(r.request.url) or r.request.resource_type in ['image','media','font','stylesheet']:r.abort();return
    request_count[0]+=1
    if request_count[0]>60:r.abort()
    else:r.continue_()
   context.route('**/*',route)
   def response(r):
    u=urllib.parse.urlsplit(r.url);item={'host':u.hostname,'path':u.path,'httpStatus':r.status}
    try:
     if r.request.resource_type in ['document','xhr','fetch']:
      body=r.body()
      if len(body)>MAX_BYTES:raise ValueError('source_response_too_large')
      item.update(bytes=len(body),sha256=sha(body))
    except Exception as error:item['bodyError']=type(error).__name__
    trace.append(item)
   page.on('response',response)
   parent=None;temporary=False
   try:parent=page.goto(INDEX,wait_until='domcontentloaded',timeout=45000)
   except Exception as error:
    report['liveParentAttempt']={'error':type(error).__name__,'reason':str(error)[:250]}
    temporary=type(error).__name__=='TimeoutError'
    if not temporary:raise
   if parent is not None:
    raw=parent.body();report['liveParentAttempt']={'httpStatus':parent.status,'sha256':sha(raw),'bytes':len(raw)}
    if len(raw)>2000000:raise ValueError('official_parent_too_large')
    (out/'official-parent-attempt.html').write_bytes(raw)
    if parent.status==200:
     # A readable removal/changed link always wins over a saved authority.
     link=app_link(raw.decode('utf8'),request['reviewedPublicAppUrl']);at=int(time.time()*1000);authority={'sourceUrl':INDEX,'checkedAt':at,'expiresAt':at+86400000,'sha256':sha(raw),'method':'current-live-official-parent'}
    elif parent.status in [408,425,429,500,502,503,504]:temporary=True
    else:raise ValueError('official_parent_denied_or_removed')
   if temporary:
    meta=json.loads(pathlib.Path(request['reviewedAuthorityMetadata']).read_text());original=pathlib.Path(meta['originalFile']).resolve()
    if not original.is_relative_to(pathlib.Path.cwd().resolve()):raise ValueError('authority_path_escape')
    raw=original.read_bytes();link=authority_snapshot(raw,meta,request['reviewedPublicAppUrl'],int(time.time()*1000));authority={**meta,'method':'previously-reviewed-official-parent-during-temporary-unavailability'}
    (out/'reviewed-authority-original.html').write_bytes(raw)
   report['officialParent']=authority
   report['officialAppLink']=link
   app=page.goto(link['url'],wait_until='domcontentloaded',timeout=45000)
   if not app or app.status!=200:raise ValueError('anonymous_public_app_unavailable')
   data=None;deadline=time.monotonic()+120
   while time.monotonic()<deadline:
    for frame in page.frames:
     try:
      value=frame.evaluate("()=>typeof streetData!=='undefined'&&Array.isArray(streetData)&&streetData.length?streetData:null")
      if value:data=value;break
     except Exception:pass
    if data is not None:break
    page.wait_for_timeout(500)
   if data is None:raise ValueError('anonymous_public_getData_did_not_complete')
   canonical=json.dumps(data,ensure_ascii=False,separators=(',',':')).encode();rows,headers=project(data)
   checked=int(time.time()*1000);expires=min(checked+86400000,authority['expiresAt'])
   if checked>=expires:raise ValueError('authority_expired_during_fresh_data_read')
   projection={'schemaVersion':1,'operatorId':'zaporizhzhia','regionId':'UA-23','settlement':'Запоріжжя','sourceUrl':link['url'],'checkedAt':checked,'expiresAt':expires,'authority':authority,'originalBusinessDataSha256':sha(canonical),'projection':'columns0street,1house,2GPV,boolean(column3ZOVA); column4GAV/extra columns never used for GPV; no raw exemption or extra fields persisted','columns':['street','house','gpv','hasPartialExemptions'],'rows':rows}
   encoded=json.dumps(projection,ensure_ascii=False,separators=(',',':')).encode();(out/'anonymous-public-address-projection.json').write_bytes(encoded+b'\n');page.screenshot(path=str(out/'official-public-app.png'),full_page=False)
   report.update(captureComplete=True,originalBusinessRows=len(data),projectedRows=len(rows),headerRowsExcluded=headers,projectionSha256=sha(encoded+b'\n'),originalBusinessDataSha256=sha(canonical),requestCount=request_count[0],recordClaims=0,elapsedSeconds=round(time.monotonic()-start,3))
   browser.close()
 except Exception as error:report.update(captureComplete=False,error=type(error).__name__,reason=str(error)[:250],elapsedSeconds=round(time.monotonic()-start,3))
 (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:report.get(k) for k in ['captureComplete','projectedRows','error','reason','elapsedSeconds']},ensure_ascii=False))
 if not report.get('captureComplete'):raise SystemExit(2)
if __name__=='__main__':main()
