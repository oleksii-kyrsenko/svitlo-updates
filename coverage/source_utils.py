"""Public-source helpers. No application modules, account persistence or address fixtures."""
import datetime,hashlib,html,http.cookiejar,json,re,time,urllib.parse,urllib.request
from pathlib import Path
UA='KolySvitloPublicCoverage/1.0 (+https://github.com/oleksii-kyrsenko/svitlo-updates)'
def clean(value):return re.sub(r'\s+',' ',html.unescape(re.sub('<[^>]*>',' ',str(value or '')))).strip()
def locality(value):return re.sub(r'^(?:м\.|с\.|смт\.?|с-ще|місто|село|селище)\s*','',clean(value).casefold()).strip()
class Fetch:
 def __init__(self,budget=100):self.budget=budget;self.deadline=time.monotonic()+180;self.calls=0;self.trace=[];self.opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
 def text(self,url,fields=None):
  if self.calls>=self.budget or time.monotonic()>self.deadline:raise ValueError('request_budget')
  from request_budget import throttle
  throttle(url)
  self.calls+=1;data=urllib.parse.urlencode(fields).encode() if fields is not None else None
  req=urllib.request.Request(url,data=data,headers={'User-Agent':'Mozilla/5.0','Accept':'application/json,text/html','Accept-Language':'uk','Content-Type':'application/x-www-form-urlencoded'})
  started=time.monotonic();item={'path':urllib.parse.urlsplit(url).path,'method':'POST' if fields is not None else 'GET'}
  try:
   with self.opener.open(req,timeout=20) as r:
    body=r.read(8_000_001)
    if len(body)>8_000_000:raise ValueError('source_size_budget')
    charset=r.headers.get_content_charset() or ('cp1251' if re.search(rb'charset\s*=\s*["\x27]?windows-1251',body[:2000],re.I) else 'utf-8');item.update(status=r.status,bytes=len(body));return body.decode(charset,'replace')
  except Exception as e:item.update(error=type(e).__name__,status=getattr(e,'code',None));raise
  finally:item['elapsedMs']=int((time.monotonic()-started)*1000);self.trace.append(item)
 def json(self,url,fields=None):return json.loads(self.text(url,fields))

def record(operator,region,settlement,community,street,house,queue,url,now,identity=None):
 street=re.sub(r'\b(вул|просп|пров|пл|бульв|бул)\.(?=\S)',r'\1. ',street,flags=re.I)
 values=[settlement,community,street,house,queue]
 if any(not isinstance(v,str) or not v.strip() for v in values) or len(house)>30 or not re.fullmatch(r'[1-9]\d?(?:\.\d{1,2})?',queue):return None
 quote=f'{settlement}, {street}, буд. {house}: черга {queue}'
 return {'id':hashlib.sha256((operator+'|'+(identity or '|'.join(values[:4]))).encode()).hexdigest()[:24],'regionId':region,'settlement':settlement,'community':community,'street':street,'scope':'house','houses':[house],'queue':queue,'sourceUrl':url,'quote':quote,'quoteType':'structured-official-fields','checkedAt':now,'expiresAt':now+86400000,'official':True}
