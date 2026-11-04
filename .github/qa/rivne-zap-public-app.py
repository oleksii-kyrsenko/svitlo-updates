"""Read the operator-linked anonymous Zaporizhzhia Apps Script dictionary.

This is source-only evidence, not Android coverage and not a signed publication.
No address, account or EIC is submitted. The official page itself calls getData.
"""
import argparse, hashlib, json, pathlib, re, time, urllib.parse
from playwright.sync_api import sync_playwright

INDEX='https://www.zoe.com.ua/outage/'
MAX_BYTES=10000000
def sha(raw):return hashlib.sha256(raw).hexdigest()
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
    request_count[0]+=1
    if request_count[0]>60 or not allowed(r.request.url) or r.request.resource_type in ['image','media','font']:r.abort()
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
   parent=page.goto(INDEX,wait_until='domcontentloaded',timeout=45000)
   if not parent or parent.status!=200:raise ValueError('official_parent_unavailable')
   raw=parent.body()
   if len(raw)>2000000:raise ValueError('official_parent_too_large')
   (out/'official-parent.html').write_bytes(raw);report['officialParent']={'url':page.url,'sha256':sha(raw),'bytes':len(raw),'httpStatus':parent.status}
   candidates=page.locator('a').evaluate_all("nodes=>nodes.map(n=>({url:n.href,label:n.textContent.trim()}))")
   links=[v for v in candidates if re.search(r'Дізнатися\s+свою\s+чергу.*м\.\s*Запоріжжя',v['label'],re.I) and re.fullmatch(r'https://script\.google\.com/macros/s/[-\w]+/exec',v['url'])]
   if len({v['url'] for v in links})!=1:raise ValueError('official_anonymous_city_app_link_not_unique')
   link=links[0]
   if link['url']!=request['reviewedPublicAppUrl']:raise ValueError('official_public_app_resource_changed_review_required')
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
   projection={'schemaVersion':1,'operatorId':'zaporizhzhia','regionId':'UA-23','settlement':'Запоріжжя','sourceUrl':link['url'],'checkedAt':int(time.time()*1000),'originalBusinessDataSha256':sha(canonical),'projection':'columns0street,1house,2GPV,boolean(column3ZOVA); column4GAV/extra columns never used for GPV; no raw exemption or extra fields persisted','columns':['street','house','gpv','hasPartialExemptions'],'rows':rows}
   encoded=json.dumps(projection,ensure_ascii=False,separators=(',',':')).encode();(out/'anonymous-public-address-projection.json').write_bytes(encoded+b'\n');page.screenshot(path=str(out/'official-public-app.png'),full_page=False)
   report.update(captureComplete=True,originalBusinessRows=len(data),projectedRows=len(rows),headerRowsExcluded=headers,projectionSha256=sha(encoded+b'\n'),originalBusinessDataSha256=sha(canonical),requestCount=request_count[0],recordClaims=0,elapsedSeconds=round(time.monotonic()-start,3))
   browser.close()
 except Exception as error:report.update(captureComplete=False,error=type(error).__name__,reason=str(error)[:250],elapsedSeconds=round(time.monotonic()-start,3))
 (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:report.get(k) for k in ['captureComplete','projectedRows','error','reason','elapsedSeconds']},ensure_ascii=False))
 if not report.get('captureComplete'):raise SystemExit(2)
if __name__=='__main__':main()
