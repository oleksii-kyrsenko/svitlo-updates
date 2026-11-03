"""Capture anonymous official responses for local pinned-runtime replay.

No application implementation, stored queue values, authenticated browsing,
CAPTCHA solving or subscriber identifiers belong in these public artifacts.
"""
import argparse,base64,hashlib,json,re,time,urllib.parse
from datetime import datetime,timezone
from pathlib import Path
from zoneinfo import ZoneInfo

MAX_RESPONSE=12*1024*1024
COMMON={'accept':'application/json,text/html','accept-language':'uk'}
CHERKASY_HEADERS={'accept':'application/json','user-agent':'Svitlo/0.1.4 (ua.svitlo.app.testing)'}
DTEK='https://www.dtek-dnem.com.ua'
CHERKASY_API='https://cabinet.cherkasyoblenergo.com/api_new/disconn.php'

class Stop(Exception):pass

def digest(b):return hashlib.sha256(b).hexdigest()
def canonical(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def stamp():return int(datetime.now(timezone.utc).timestamp()*1000)
def normal(s):return re.sub(r'\s+',' ',re.sub(r"[’ʼ'`.,()]",' ',str(s).casefold())).strip()
def locality(s):return re.sub(r'^(?:м\.?|місто|село|с\.)\s+','',normal(s))
def street_tokens(s):return sorted(w for w in normal(s).split() if w not in ['вул','вулиця','пров','провулок','просп','проспект','бульвар','бул','площа','пл'])
def street_candidate(a,b):
 x,y=street_tokens(a),street_tokens(b)
 return x==y or bool(set(w for w in x if len(w)>=5)&set(w for w in y if len(w)>=5))
def house_key(s):return re.sub(r'(\d)[‐‑‒–—-](?=[а-яіїєґ]$)','\\1',re.sub(r'\s+','',str(s).casefold()).translate(str.maketrans('aceopx','асеорх')))
def values(x):return list(x.values()) if isinstance(x,dict) else x if isinstance(x,list) else []
def query(params):return urllib.parse.urlencode(sorted((str(k),str(v)) for k,v in params.items()),safe='*')
def encoded_body(params):return urllib.parse.urlencode(params,safe='*')
def request_failure(error):
 # Match fixed diagnostic classes without retaining the original exception.
 # Browser errors may embed a URL containing a transient subscriber reference.
 value=str(error).lower()
 for pattern,reason in [
  (r'err_cert|certificate|cert_has_expired|unable.to.verify|self.signed','official-tls-certificate-error'),
  (r'unsupported.protocol|protocol.version|ssl_error|err_ssl|tlsv1_alert|wrong.version.number|version.or.cipher|eproto|unsafe.legacy.renegotiation','official-tls-protocol-error'),
  (r'timed?.?out|timeout|etimedout','official-request-timeout'),
  (r'err_name|enotfound|eai_again|name.not.resolved','official-dns-unavailable'),
  (r'econnreset|connection.reset|socket.hang.up','official-connection-reset')]:
  if re.search(pattern,value):return reason
 return 'official-request-unavailable'
def clean_error(error):return {'kind':type(error).__name__,'reason':str(error) if isinstance(error,Stop) else 'official-request-failed'}

def sanitize(url,value,pseudonyms):
 parsed=urllib.parse.urlsplit(url);op=dict(urllib.parse.parse_qsl(parsed.query)).get('op')
 if parsed.hostname=='cabinet.cherkasyoblenergo.com':
  if op=='ls_list_by_addr':
   out=[]
   for row in values(value):
    if not isinstance(row,dict) or not row.get('LS'):continue
    raw=str(row['LS']);pseudonyms.setdefault(raw,'qa-account-'+str(len(pseudonyms)+1));out.append({'LS':pseudonyms[raw]})
   return out
  if op=='disconn_by_ls':
   def section(value):
    text=str(value)
    for raw in pseudonyms:text=text.replace(raw,'[redacted-account]')
    return re.sub(r'(?<![A-Za-z0-9])\d{2}[A-Z][A-Z0-9]{13}(?![A-Za-z0-9])','[redacted-eic]',text)
   return {'DISCONN_QUEUQ':[{'QUEUE_INFO':section(r.get('QUEUE_INFO',''))} for r in values(value.get('DISCONN_QUEUQ')) if isinstance(r,dict)]}
  allowed={'department_list':{'ID','NAME'},'city_list':{'ID','NAME','postcode','community','district','regionId','katottg'},'street_list':{'ID','NAME'},'house_list':{'HOUSE'}}.get(op)
  if allowed:return [{k:v for k,v in r.items() if k in allowed} for r in values(value) if isinstance(r,dict)]
 if parsed.hostname=='www.dtek-dnem.com.ua' and parsed.path=='/ua/ajax':
  if not isinstance(value,dict):raise Stop('invalid-official-house-payload')
  return {'result':value.get('result'),'data':{str(h):{'sub_type_reason':r.get('sub_type_reason')} for h,r in (value.get('data') or {}).items() if isinstance(r,dict)}}
 def public(x):
  if isinstance(x,list):return [public(v) for v in x]
  if isinstance(x,dict):return {k:public(v) for k,v in x.items() if not re.search(r'eic|account|subscriber|customer|abon|personal|phone|email|login|password|^ls$',k,re.I)}
  return x
 return public(value)

class Capture:
 def __init__(self,context,page,folder,limit=160):
  self.context,self.page,self.folder=context,page,folder;folder.mkdir(parents=True,exist_ok=True)
  self.limit=limit;self.count=0;self.entries=[];self.proofs=[];self.last={};self.pseudonyms={}
 def request(self,url,headers,body='',network_url=None,network_body=None,fetch_in_page=False):
  public=urllib.parse.urlsplit(url);real=urllib.parse.urlsplit(network_url or url)
  allowed_hosts=['www.dtek-dnem.com.ua','cabinet.cherkasyoblenergo.com','app.yasno.ua']
  if real.scheme!='https' or real.hostname not in allowed_hosts or public.scheme!='https' or public.hostname!=real.hostname:raise Stop('unapproved-official-host')
  if real.username or real.password or real.fragment or public.username or public.password or public.fragment or real.path!=public.path:raise Stop('unapproved-official-url')
  if real.hostname=='www.dtek-dnem.com.ua' and real.path not in ['/ua/shutdowns','/ua/ajax']:raise Stop('unapproved-official-path')
  if real.hostname=='cabinet.cherkasyoblenergo.com' and real.path!='/api_new/disconn.php':raise Stop('unapproved-official-path')
  if real.hostname=='app.yasno.ua' and not real.path.startswith('/api/blackout-service/public/shutdowns/addresses/v2/'):raise Stop('unapproved-official-path')
  if network_url:
   original=dict(urllib.parse.parse_qsl(public.query));actual=dict(urllib.parse.parse_qsl(real.query))
   if original.get('op')!='disconn_by_ls' or real.hostname!='cabinet.cherkasyoblenergo.com' or {k:v for k,v in original.items() if k!='abon_ls'}!={k:v for k,v in actual.items() if k!='abon_ls'}:raise Stop('unapproved-private-reference-mapping')
  if any(k.lower() in ['cookie','authorization'] for k in headers):raise Stop('credential-header-forbidden')
  if self.count>=self.limit:raise Stop('request-budget')
  delay=self.last.get(real.hostname,0)+1.05-time.monotonic()
  if delay>0:time.sleep(delay)
  self.last[real.hostname]=time.monotonic();self.count+=1;at=stamp();method='POST' if body else 'GET'
  target=network_url or url;sent=network_body if network_body is not None else body
  try:
   if fetch_in_page:
    answer=self.page.evaluate("""async ({url,method,headers,body})=>{const r=await fetch(url,{method,headers,credentials:'include',...(method==='POST'?{body}:{} )});return {status:r.status,contentType:r.headers.get('content-type')||'',text:await r.text()};}""",{'url':target,'method':method,'headers':headers,'body':sent})
    raw=answer['text'].encode();status=answer['status'];kind=answer['contentType']
   else:
    response=self.context.request.fetch(target,method=method,headers=headers,data=sent if method=='POST' else None,timeout=25000)
    if int(response.headers.get('content-length','0') or 0)>MAX_RESPONSE:raise Stop('source-response-budget')
    raw=response.body();status=response.status;kind=response.headers.get('content-type','')
  except Stop:raise
  except Exception as error:raise Stop(request_failure(error))
  if len(raw)>MAX_RESPONSE:raise Stop('source-response-budget')
  try:original=json.loads(raw);safe=sanitize(url,original,self.pseudonyms);saved=json.dumps(safe,ensure_ascii=False,separators=(',',':')).encode();kind='application/json;charset=utf-8'
  except json.JSONDecodeError:
   private_route=dict(urllib.parse.parse_qsl(public.query)).get('op') in ['ls_list_by_addr','disconn_by_ls']
   saved=json.dumps({'redactedPrivateResponse':True,'httpStatus':status}).encode() if private_route else raw
   safe=None
   if private_route:kind='application/json;charset=utf-8'
  # No raw body from subscriber-related routes is persisted. Keep only a hash
  # of the original and the sanitized queue/address fields used by both runtimes.
  filename=f'response-{self.count:03d}.json' if safe is not None else f'response-{self.count:03d}.html'
  (self.folder/filename).write_bytes(saved)
  self.proofs.append({'requestNumber':self.count,'sourceUrl':url,'httpStatus':status,'observedAt':at,'originalResponseSha256':digest(raw),'sanitizedResponseSha256':digest(saved),'artifact':filename,'subscriberDataPersisted':False})
  self.entries.append({'request':{'method':method,'url':url,'body':body,'headers':headers},'observedAt':at,'status':status,'headers':{'content-type':kind or 'application/octet-stream'},'bodyBase64':base64.b64encode(saved).decode()})
  if status<200 or status>=300:raise Stop('official-http-'+str(status))
  if safe is None and dict(urllib.parse.parse_qsl(public.query)).get('op') in ['ls_list_by_addr','disconn_by_ls']:raise Stop('official-private-response-format-invalid')
  return safe,raw.decode('utf-8','replace')
 def warm(self,url,expect_dtek=False):
  try:self.page.goto(url,wait_until='domcontentloaded',timeout=45000)
  except Exception:raise Stop('official-page-unavailable')
  # Allow ordinary public page scripts; no stealth, injected challenge token,
  # logged-in profile or CAPTCHA solver is installed.
  until=time.monotonic()+30
  while time.monotonic()<until:
   if self.visible_challenge():raise Stop('visible-captcha-or-login-stop')
   if not expect_dtek or self.page.evaluate("typeof DisconSchedule!=='undefined'&&Boolean(DisconSchedule.streets)"):break
   self.page.wait_for_timeout(1000)
  if self.visible_challenge():raise Stop('visible-captcha-or-login-stop')
  try:self.page.screenshot(path=str(self.folder/'ordinary-page.png'),full_page=False)
  except Exception:pass
 def visible_challenge(self):
  for selector in ['iframe[src*="recaptcha"]','iframe[src*="challenges.cloudflare.com"]','.g-recaptcha','.cf-turnstile','input[type="password"]']:
   try:
    if any(element.is_visible() for element in self.page.locator(selector).all()):return True
   except Exception:pass
  return False

def assignment(text,label):
 match=re.search(re.escape(label)+r'\s*=\s*',text)
 if not match:raise Stop('official-dictionary-not-published-after-ordinary-browser')
 try:return json.JSONDecoder().raw_decode(text[match.end():])[0]
 except ValueError:raise Stop('official-dictionary-format-changed')

def dtek(capture,case):
 page_url=DTEK+'/ua/shutdowns';capture.warm(page_url,expect_dtek=True)
 # The captured YASNO dictionary requests are public protocol probes from the
 # earlier failed runtime trace; there are no expected queues in these inputs.
 for probe in case.get('publicDictionaryProbes',[]):
  u=urllib.parse.urlsplit(probe['url'])
  if u.hostname!='app.yasno.ua' or not u.path.startswith('/api/blackout-service/public/shutdowns/addresses/v2/'):raise Stop('unapproved-dictionary-probe')
  capture.request(probe['url'],probe['headers'])
 _,html=capture.request(page_url,COMMON,fetch_in_page=True)
 streets=assignment(html,'DisconSchedule.streets')
 cities=[name for name in streets if locality(name)==locality(case['city'])]
 if len(cities)!=1:raise Stop('official-city-not-unique')
 city=cities[0];found=[s for s in streets[city] if street_tokens(s)==street_tokens(case['input']['addressParts']['street'])]
 if len(found)!=1:raise Stop('official-street-not-unique')
 fact=assignment(html,'DisconSchedule.fact');token=re.search(r'<meta\b[^>]*name=["\']csrf-token["\'][^>]*content=["\']([^"\']+)',html,re.I);param=re.search(r'<meta\b[^>]*name=["\']csrf-param["\'][^>]*content=["\']([^"\']+)',html,re.I)
 body={'method':'getHomeNum','data[0][name]':'city','data[0][value]':city,'data[1][name]':'street','data[1][value]':found[0],'data[2][name]':'updateFact','data[2][value]':fact.get('update','')}
 if token:body[param[1] if param else '_csrf']=token[1]
 data,_=capture.request(DTEK+'/ua/ajax',{**COMMON,'content-type':'application/x-www-form-urlencoded;charset=UTF-8','x-requested-with':'XMLHttpRequest'},encoded_body(body),fetch_in_page=True)
 if not isinstance(data,dict) or data.get('result') is not True or not isinstance(data.get('data'),dict):raise Stop('official-house-response-invalid')
 if not any(house_key(h)==house_key(case['exactHouse']) for h in data['data']):raise Stop('exact-official-house-not-published')

def cherkasy(capture,case,recorded_at):
 capture.warm('https://www.cherkasyoblenergo.com/off')
 def q(params,private_id=None):
  public=CHERKASY_API+'?'+query(params);real=None
  if private_id is not None:real=CHERKASY_API+'?'+query({**params,'abon_ls':private_id})
  data,_=capture.request(public,CHERKASY_HEADERS,network_url=real);return data
 departments=values(q({'op':'department_list'}));cities=[]
 for dep in departments:
  for city in values(q({'op':'city_list','dept_id':dep['ID']})):
   if normal(city.get('NAME'))==normal(case['city']):cities.append(city)
 if not cities:raise Stop('official-city-not-published')
 selected=case['input'].get('officialCityId');matches=[]
 for city in cities:
  streets=values(q({'op':'street_list','city_id':city['ID'],'search_name':''}));candidates=[s for s in streets if street_candidate(case['input']['addressParts']['street'],s.get('NAME',''))]
  if len(candidates)>6:raise Stop('official-street-discovery-too-broad')
  for street in candidates:
   for house in values(q({'op':'house_list','street_id':street['ID'],'search_name':''})):
    if house_key(house.get('HOUSE'))==house_key(case['exactHouse']):matches.append((city,street,house))
 chosen=[m for m in matches if not selected or str(m[0]['ID'])==str(selected)]
 if not chosen:raise Stop('exact-official-house-not-published')
 # The only raw account values are read transiently from an anonymous public
 # response and mapped immediately. Capture.request persists sanitized fields.
 for city,street,house in chosen:
  params={'op':'ls_list_by_addr','street_id':street['ID'],'house':house['HOUSE']};url=CHERKASY_API+'?'+query(params)
  accounts=q(params)
  reverse={token:raw for raw,token in capture.pseudonyms.items()}
  if not accounts or len(accounts)>8:raise Stop('official-connections-not-unique-or-missing')
  date=datetime.fromtimestamp(recorded_at/1000,ZoneInfo('Europe/Kyiv')).strftime('%d.%m.%Y')
  for account in accounts:
   token=account.get('LS');raw=reverse.get(token)
   if not raw:raise Stop('official-account-pseudonym-missing')
   q({'op':'disconn_by_ls','disconn_selector':'2','n_date':date,'k_date':date,'abon_ls':token},private_id=raw)

def run(args):
 from playwright.sync_api import sync_playwright
 config=json.loads(Path(args.inputs).read_text());out=Path(args.out);out.mkdir(parents=True,exist_ok=True);reports=[]
 selected=set(filter(None,args.case_ids.split(',')))
 if selected-set(c['id'] for c in config['cases']):raise ValueError('unknown-frozen-case-selection')
 if selected:config['cases']=[c for c in config['cases'] if c['id'] in selected]
 with sync_playwright() as p:
  browser=p.chromium.launch(headless=True)
  try:
   for case in config['cases']:
    recorded_at=stamp();folder=out/case['id'];context=browser.new_context(locale='uk-UA');page=context.new_page();capture=Capture(context,page,folder,args.request_limit);report={'caseId':case['id'],'operatorId':case['operatorId'],'startedAt':recorded_at,'captureComplete':False,'javascriptExecuted':True,'captchaSolved':False,'authenticated':False}
    try:
     if case['operatorId']=='dtek-dnipro':dtek(capture,case)
     elif case['operatorId']=='cherkasy':cherkasy(capture,case,recorded_at)
     else:raise Stop('unsupported-official-operator')
     report['captureComplete']=True
    except Exception as error:report['blocker']=clean_error(error)
    finally:
     snapshot={'schemaVersion':1,'kind':'sanitized-public-source-response-snapshot','privacy':'Anonymous official address/queue fragments only; subscriber identifiers pseudonymized in memory; no cookies, storage or authentication headers.','recordedAt':recorded_at,'caseId':case['id'],'addressFingerprint':case['addressFingerprint'],'input':case['input'],'baselineSha256':config['baselineSha256'],'transport':{'anonymousSession':True,'javascriptExecuted':True,'cookieValuesPersisted':False},'entries':capture.entries}
     (folder/'source-snapshot.json').write_text(json.dumps(snapshot,ensure_ascii=False,separators=(',',':'))+'\n');report.update({'completedAt':stamp(),'requests':capture.count,'sourceSnapshotSha256':digest((folder/'source-snapshot.json').read_bytes()),'proofs':capture.proofs});(folder/'capture-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');reports.append(report);context.close()
    print(json.dumps({k:report[k] for k in ['caseId','captureComplete','requests']},ensure_ascii=False),flush=True)
  finally:browser.close()
 (out/'report.json').write_text(json.dumps({'schemaVersion':1,'method':'ordinary-chromium-source-only-capture-no-application-code','queueCoverageClaim':False,'cases':reports},ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--inputs',default='.github/qa/browser-regression-inputs.json');parser.add_argument('--out',default='browser-regression-evidence');parser.add_argument('--request-limit',type=int,default=160);parser.add_argument('--case-ids',default='');args=parser.parse_args()
 if not 1<=args.request_limit<=200:raise ValueError('request_limit')
 run(args)
