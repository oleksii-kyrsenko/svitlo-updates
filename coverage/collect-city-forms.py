"""Public city-form collectors; no application imports or subscriber queries.

Official dictionary IDs and names are discovered for each run. A resumable
request boundary never means the entire city has been covered.
"""
import argparse,hashlib,html,http.cookiejar,json,re,time,unicodedata,urllib.error,urllib.parse,urllib.request
from pathlib import Path
from html.parser import HTMLParser
from city_crawl import city_key,request_limit,scoped_state,search_inventory
from source_utils import clean,record

CONFIG={
 'kirovohrad':('UA-35','https://kiroe.com.ua/electricity-blackout'),
 'volyn':('UA-07','https://www.energy.volyn.ua/spozhyvacham/perervy-u-elektropostachanni/cherga/'),
 'prykarpattia':('UA-26','https://svitlo.oe.if.ua/'),
 'vinnytsia':('UA-05','https://www.voe.com.ua/disconnection/detailed'),
}

class HTTP:
 def __init__(self,limit=120):
  self.limit=limit;self.calls=0;self.deadline=time.monotonic()+480;self.trace=[]
  self.opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
 def text(self,url,fields=None,*,ajax=False,referer=None,accepted=()):
  if self.calls>=self.limit or time.monotonic()>=self.deadline:raise ValueError('request_budget')
  from request_budget import throttle
  throttle(url);self.calls+=1
  headers={'User-Agent':'Mozilla/5.0 (KolySvitlo public source collector)','Accept-Language':'uk','Accept':'application/json,text/html'}
  if fields is not None:headers['Content-Type']='application/x-www-form-urlencoded;charset=UTF-8'
  if ajax:headers['X-Requested-With']='XMLHttpRequest'
  if referer:headers['Referer']=referer
  req=urllib.request.Request(url,data=urllib.parse.urlencode(fields).encode() if fields is not None else None,headers=headers)
  event={'path':urllib.parse.urlsplit(url).path,'method':'POST' if fields is not None else 'GET','checkedAt':int(time.time()*1000)}
  try:
   try:response=self.opener.open(req,timeout=25)
   except urllib.error.HTTPError as e:
    if e.code not in accepted:raise
    response=e
   with response:
    raw=response.read(8_000_001)
    if len(raw)>8_000_000:raise ValueError('source_response_limit')
    event.update(httpStatus=response.code,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
    charset=response.headers.get_content_charset() or ('cp1251' if re.search(rb'charset\s*=\s*["\x27]?windows-1251',raw[:2500],re.I) else 'utf-8')
    return raw.decode(charset,'replace')
  except Exception as e:event.update(error=type(e).__name__,httpStatus=getattr(e,'code',None));raise
  finally:self.trace.append(event)
 def json(self,url,fields=None,**options):return json.loads(self.text(url,fields,**options))


def geography(operator,target):
 data=json.loads(Path(__file__).with_name('capital-geography.json').read_text())
 matches=[c for c in data['cities'] if c['regionId']==CONFIG[operator][0] and city_key(c['settlement'])==city_key(target)]
 if len(matches)!=1 or not matches[0].get('community'):raise ValueError('verified_city_context_required')
 return matches[0]


def house(value):
 value=clean(value)
 return value if re.fullmatch(r'\d{1,4}(?:[ -]?[А-Яа-яІіЇїЄєҐґA-Za-z])?(?:/\d{1,4}[А-Яа-яІіЇїЄєҐґA-Za-z]?)?',value) else None


def house_key(value):
 value=re.sub(r'[\s№]','',unicodedata.normalize('NFKC',str(value))).casefold()
 value=value.translate(str.maketrans({'a':'а','c':'с','e':'е','o':'о','p':'р','x':'х'}))
 return re.sub(r'(\d)[‐‑‒–—-](?=[а-яіїєґ]$)',r'\1',value)
def queue(value):
 value=clean(value)
 return value if re.fullmatch(r'[1-9]\d?(?:\.[12])?',value) else None


def consensus_rows(items,house_field,queue_field):
 grouped={}
 for item in items:
  h=house(item.get(house_field))
  if h:grouped.setdefault(house_key(h),[]).append((h,queue(item.get(queue_field))))
 result=[]
 for group in grouped.values():
  values=[value for _,value in group]
  result.append((group[0][0],values[0] if all(values) and len(set(values))==1 else None))
 return result


def emitted(operator,geo,street,house_name,q,url,observed,city_id=None,street_id=None):
 item=record(operator,geo['regionId'],geo['settlement'],geo['community'],street,house_name,q,url,observed)
 if not item:return None
 if city_id is not None:item['providerCityId']=str(city_id)
 if street_id is not None:item['providerStreetId']=str(street_id)
 if city_id is not None and street_id is not None:item['officialCityId']=str(city_id)+':'+str(street_id)
 return item


def observe(geo,street,house_name,street_id=None):
 return {'regionId':geo['regionId'],'settlement':geo['settlement'],'community':geo['community'],'street':street,'house':house_name,**({'providerStreetId':str(street_id)} if street_id is not None else {})}


def kirovohrad(http,geo,state):
 base=CONFIG['kirovohrad'][1];page=http.text(base);token=re.search(r'ajaxToken:\s*["\']([^"\']+)',page)
 select=re.search(r'<select\b[^>]*id=["\']fn_office["\'][^>]*>(.*?)</select>',page,re.I|re.S)
 if not token or not select:raise ValueError('official_city_form_changed')
 offices=[{'id':m[1],'name':clean(m[2])} for m in re.finditer(r'<option\b[^>]*value=["\'](\d+)["\'][^>]*>(.*?)</option>',select[1],re.I|re.S)]
 # Office labels explicitly name hromadas. Narrow only by the sourced community
 # stem, never by a built-in city/office numeric ID.
 stem=re.sub(r'\s+(?:міська|селищна|сільська|територіальна|громада)\b','',geo['community'],flags=re.I).strip()
 narrowed=[o for o in offices if city_key(o['name'])==city_key(stem)]
 if len(narrowed)==1:offices=narrowed
 def query(path):
  value=http.json(base+path+'?t='+str(int(time.time()*1000)),{'ajax':1,'token':token[1]},ajax=True,referer=base)
  if value.get('success') is not True or not isinstance(value.get('data'),list):raise ValueError('unsupported_city_dictionary')
  return value['data']
 cities=[]
 for office in offices:
  for c in query('/city/'+office['id']):
   if city_key(c.get('CityName'))==city_key(geo['settlement']):cities.append(c)
 unique={str(c['CityId']):c for c in cities if c.get('CityId') is not None}
 if len(unique)!=1:raise ValueError('official_city_not_unique')
 city=next(iter(unique.values()));city_id=str(city['CityId']);streets=query('/street/'+city_id)
 if any(not isinstance(s,dict) or not s.get('StreetId') for s in streets):raise ValueError('invalid_street_dictionary')
 streets=sorted(streets,key=lambda s:str(s['StreetId']));position=int(state.get('streetIndex',0))%max(1,len(streets));rows=[];observed=[];completed=[];errors=[];start=position
 while position<len(streets):
  street=streets[position];name=clean(' '.join([str(street.get('StreetType','')),str(street.get('StreetName',''))]))
  try:
   raw=query('/house/'+str(street['StreetId']))
   # An endpoint returning houses of another city/street is a source failure,
   # not permission to attach those houses to the current street.
   if any(str(h.get('CityId',city_id))!=city_id or str(h.get('StreetId',street['StreetId']))!=str(street['StreetId']) for h in raw):raise ValueError('house_dictionary_crosses_street')
   at=int(time.time()*1000)
   for h,q in consensus_rows(raw,'HouseName','chergGpv'):
    observed.append(observe(geo,name,h,street['StreetId']))
    if q:
     r=emitted('kirovohrad',geo,name,h,q,base,at,city_id,street['StreetId'])
     if r:rows.append(r)
   completed.append(city_id+':'+str(street['StreetId']));position+=1;state['streetIndex']=position
  except Exception as e:errors.append({'stage':'houses','streetId':str(street['StreetId']),'error':type(e).__name__,'httpStatus':getattr(e,'code',None)});break
 done=position>=len(streets)
 state['dictionaryComplete']=True;state['crawlStatus']='complete' if done else 'partial';state['knownStreets']=len(streets)
 if done:state['streetIndex']=0;state['cycles']=int(state.get('cycles',0))+1
 return rows,observed,completed,errors,{'sourceCityId':city_id,'streetsRead':len(completed),'streetsKnown':len(streets),'startedAtStreet':start}


class Table(HTMLParser):
 def __init__(self):super().__init__(convert_charrefs=True);self.rows=[];self.cells=[];self.cell=None
 def handle_starttag(self,tag,attrs):
  if tag=='tr':self.cells=[]
  if tag in ('td','th'):self.cell=''
  if tag=='br' and self.cell is not None:self.cell+=';'
 def handle_data(self,data):
  if self.cell is not None:self.cell+=data
 def handle_endtag(self,tag):
  if tag in ('td','th') and self.cell is not None:self.cells.append(clean(self.cell));self.cell=None
  if tag=='tr':self.rows.append(self.cells)


def volyn_rows(body,target,query_term=None):
 parsed=Table();parsed.feed(body)
 if not any(len(r)==6 and 'ГПВ' in r[4] and 'ГАВ' in r[5] for r in parsed.rows):
  text=clean(body)
  expected='Фільтр: Нас. пункт '+target+' + Вулиця '+str(query_term)
  form_fields=all(re.search(r'name=[\"\']'+name+r'[\"\']',body) for name in ('formCity','formStreet'))
  protected=re.search(r'_Incapsula_Resource|cf-chl-|Just a moment|captcha-delivery',body,re.I)
  if query_term is not None and form_fields and expected in text and 'Вибраної адреси у графіках не знайдено.' in text and not protected:return []
  raise ValueError('official_table_header_missing')
 out=[]
 for r in parsed.rows:
  if len(r)!=6 or city_key(r[1])!=city_key(target):continue
  raw_numbers=re.split('[,;]',r[3]);numbers=[house(s) for s in raw_numbers]
  # A partly covered row, landmark or unqualified range contributes no guessed
  # numbers. Its raw text remains available to independent source inspection.
  if not numbers:continue
  for token,h in zip(raw_numbers,numbers):
   if h:out.append({'district':r[0],'street':r[2],'house':h,'queue':r[4]})
   elif (match:=re.fullmatch(r'\s*(\d{1,4})\s*[-–—]\s*(\d{1,4})\s*',token)):
    out.append({'district':r[0],'street':r[2],'house':None,'queue':r[4],'_range':[int(match[1]),int(match[2])]})
 return out


def volyn(http,geo,state):
 base=CONFIG['volyn'][1];frontier=state.setdefault('searchTerms',list('абвгґдеєжзиіїйклмнопрстуфхцчшщьюя0123456789'));inventory=state.setdefault('streetNames',[])
 # Discovery uses ordinary one-character form searches accepted by the source.
 # Each discovered exact street gets a separate follow-up before publication.
 errors=[];discovery=min(5,max(1,http.limit//8))
 for _ in range(discovery):
  if not frontier:break
  term=frontier[0]
  try:
   items=volyn_rows(http.text(base,{'formCity':geo['settlement'],'formStreet':term}),geo['settlement'],term)
   inventory[:]=sorted(set(inventory)|{r['street'] for r in items});frontier.pop(0)
  except Exception as e:errors.append({'stage':'street_discovery','searchTerm':term,'error':type(e).__name__,'httpStatus':getattr(e,'code',None)});break
 rows=[];observed=[];completed=[];position=int(state.get('streetIndex',0))%max(1,len(inventory));count=0
 while position<len(inventory):
  street=inventory[position]
  try:
   exact=[r for r in volyn_rows(http.text(base,{'formCity':geo['settlement'],'formStreet':street}),geo['settlement'],street) if clean(r['street']).casefold()==clean(street).casefold()]
   districts={r['district'] for r in exact}
   if len(districts)>1:raise ValueError('ambiguous_official_district')
   at=int(time.time()*1000)
   for h,q in consensus_rows(exact,'house','queue'):
    number=int(re.match(r'\d+',h)[0])
    if any(r.get('_range') and r['_range'][0]<=number<=r['_range'][1] and queue(r.get('queue'))!=q for r in exact):q=None
    observed.append(observe(geo,street,h))
    if q:
     r=emitted('volyn',geo,street,h,q,base,at)
     if r:rows.append(r)
   count+=1;position+=1;state['streetIndex']=position
  except Exception as e:errors.append({'stage':'street_followup','street':street,'error':type(e).__name__,'httpStatus':getattr(e,'code',None)});break
 # The form exposes no untruncated directory contract. Exhausting this search
 # alphabet is reported separately and is not asserted to mean 100% of streets.
 state.update(dictionaryComplete=False,crawlStatus='partial',knownStreets=len(inventory),pendingSearchTerms=len(frontier))
 if position>=len(inventory):state['streetIndex']=0;state['cycles']=int(state.get('cycles',0))+1
 return rows,observed,completed,errors,{'streetFollowups':count,'discoveredStreets':len(inventory),'sourceSearchExhausted':not frontier}


def geographic_addresses(http,geo,state):
 # The source publishes a freeform form, so source-independent public geometry
 # supplies candidate spellings. Geometry never supplies a queue.
 inventory=state.get('geographicAddresses')
 observed=state.get('geographicCheckedAt',0)
 if isinstance(inventory,list) and observed>int(time.time()*1000)-7*86400000:return inventory
 relation=geo.get('osmRelation')
 if not isinstance(relation,int):raise ValueError('sourced_city_boundary_required')
 query='[out:json][timeout:50];area('+str(3600000000+relation)+')->.a;nwr["building"]["addr:street"]["addr:housenumber"](area.a);out tags center;'
 failures=[];body=None
 for base in ('https://overpass-api.de/api/interpreter','https://overpass.kumi.systems/api/interpreter'):
  try:
   body=http.json(base,{'data':query});source=base;break
  except Exception as e:failures.append(type(e).__name__)
 if body is None:raise ValueError('public_city_geometry_unavailable:'+','.join(failures))
 if not isinstance(body.get('elements'),list):raise ValueError('invalid_public_geometry')
 items={}
 for element in body['elements']:
  tags=element.get('tags',{});street=clean(tags.get('addr:street'));h=house(tags.get('addr:housenumber'))
  if not street or not h:continue
  if tags.get('addr:city') and city_key(tags['addr:city'])!=city_key(geo['settlement']):continue
  key=(street.casefold(),house_key(h))
  items[key]={'street':street,'house':h}
 inventory=sorted(items.values(),key=lambda item:hashlib.sha256((item['street']+'|'+item['house']).encode()).hexdigest())
 if len(inventory)>100000:raise ValueError('geographic_inventory_limit')
 state.update(geographicAddresses=inventory,geographicCheckedAt=int(time.time()*1000),geographicSourceUrl=source,geographicQuerySha256=hashlib.sha256(query.encode()).hexdigest())
 return inventory


def prykarpattia_queue(value):
 current=value.get('current') if isinstance(value,dict) else None
 if not isinstance(current,dict) or str(current.get('hasQueue','')).casefold()!='yes':return None
 group,sub=str(current.get('queue','')),str(current.get('subQueue',''))
 return group+'.'+sub if re.fullmatch(r'[1-9]\d?',group) and re.fullmatch(r'[12]',sub) else None


def prykarpattia(http,geo,state):
 inventory=geographic_addresses(http,geo,state);rows=[];observed=[];errors=[];position=int(state.get('addressIndex',0))%max(1,len(inventory));done=0
 while position<len(inventory):
  item=inventory[position];street=item['street'];name=re.sub(r'^(?:вулиця|вул\.?)\s+','',street,flags=re.I)
  if name==street:name=re.sub(r'\s+(?:вулиця|вул\.?)$','',street,flags=re.I)
  source='https://be-svitlo.oe.if.ua/schedule-by-search'
  try:
   value=http.json(source,{'accountNumber':'','userSearchChoice':'pob','address':','.join([geo['settlement'],name,item['house']])},ajax=True,referer=CONFIG['prykarpattia'][1],accepted=(300,))
   if not isinstance(value,dict) or not isinstance(value.get('current'),dict) or str(value['current'].get('hasQueue','')).casefold() not in ('yes','no','many'):raise ValueError('official_current_record_missing')
   q=prykarpattia_queue(value);at=int(time.time()*1000)
   observed.append(observe(geo,street,item['house']))
   if q:
    r=emitted('prykarpattia',geo,street,item['house'],q,source,at)
    if r:rows.append(r)
   done+=1;position+=1;state['addressIndex']=position
  except Exception as e:
   errors.append({'stage':'address','error':type(e).__name__,'httpStatus':getattr(e,'code',None),'street':street,'house':item['house']})
   if isinstance(e,ValueError) and str(e)=='request_budget':break
   # The official form returns404 for some geographic addresses. Keep that
   # failure explicit and move on for this cycle; never infer another queue.
   position+=1;state['addressIndex']=position
 state.update(dictionaryComplete=False,crawlStatus='partial',geographicCandidates=len(inventory))
 if position>=len(inventory):state['addressIndex']=0;state['cycles']=int(state.get('cycles',0))+1
 return rows,observed,[],errors,{'geographicCandidates':len(inventory),'officialResponsesChecked':done,'geographicSourceUrl':state.get('geographicSourceUrl'),'geographicCheckedAt':state.get('geographicCheckedAt')}


class Attributes(HTMLParser):
 def __init__(self):super().__init__(convert_charrefs=True);self.attributes={}
 def handle_starttag(self,tag,attrs):self.attributes=dict(attrs)

def attributes(value):
 parser=Attributes();parser.feed('<input '+value+'>');return parser.attributes


def drupal_form(body):
 forms=[]
 for match in re.finditer(r'<form\b([^>]*)>(.*?)</form>',body,re.I|re.S):
  if str(attributes(match[1]).get('id','')).startswith('disconnection-detailed-search-form'):forms.append(match[2])
 if len(forms)!=1:raise ValueError('official_drupal_form_missing')
 fields={}
 for match in re.finditer(r'<input\b([^>]*)>',forms[0],re.I|re.S):
  a=attributes(match[1])
  if a.get('type','').casefold()=='hidden' and a.get('name'):fields[a['name']]=a.get('value','')
 if not fields.get('form_build_id') or not fields.get('form_id'):raise ValueError('official_drupal_state_missing')
 return fields,forms[0]


def drupal_autocomplete(value):
 if not isinstance(value,list):raise ValueError('invalid_official_autocomplete')
 rows=[]
 for item in value:
  if not isinstance(item,dict) or not isinstance(item.get('value'),str):raise ValueError('invalid_official_autocomplete_row')
  identity=re.search(r'data-id=["\'](\d+)',str(item.get('label','')))
  if not identity:raise ValueError('official_autocomplete_id_missing')
  name=re.sub(r'^([мс])\.\.\s*',r'\1. ',item['value'])
  name=re.sub(r'^(вулиця|провулок)\.\s*',r'\1 ',name,flags=re.I)
  rows.append({'id':identity[1],'value':item['value'],'name':name})
 return rows


def drupal_queue(form):
 marker=None
 for match in re.finditer(r'<div\b([^>]*)>',form,re.I|re.S):
  if 'disconnection-detailed-table' in str(attributes(match[1]).get('class','')).split():marker=match.end();break
 if marker is None:return None
 # Only the initial answer paragraphs belong to the search result. The page's
 # schedule table, legend, menu and unrelated news cannot supply a queue.
 heading=re.match(r'\s*((?:<p\b[^>]*>.*?</p>\s*)+)',form[marker:],re.I|re.S)
 if not heading:return None
 values=re.findall(r'(?<![\d.])([1-6]\.[12])\s*черга(?:\s|$)',clean(heading[1]),re.I)
 return values[0] if values and len(set(values))==1 else None


def vinnytsia(http,geo,state):
 base=CONFIG['vinnytsia'][1];fields,form=drupal_form(http.text(base))
 def post(selected,search=False):
  nonlocal fields
  operation={'search':'Показати'} if search else {'refresh':'Refresh'}
  payload=http.text(base+'?ajax_form=1&_wrapper_format=drupal_ajax',{**fields,**selected,**operation,'_drupal_ajax':'1','_triggering_element_name':'search' if search else 'refresh','_triggering_element_value':'Показати' if search else 'Refresh'},ajax=True,referer=base)
  wrapped=re.fullmatch(r'\s*<textarea[^>]*>(.*?)</textarea>\s*',payload,re.I|re.S)
  commands=json.loads(html.unescape(wrapped[1]) if wrapped else payload)
  if not isinstance(commands,list):raise ValueError('invalid_drupal_commands')
  matches=[c['data'] for c in commands if isinstance(c,dict) and c.get('command')=='insert' and isinstance(c.get('data'),str) and 'disconnection-detailed-search-form' in c['data']]
  if len(matches)!=1:raise ValueError('official_drupal_answer_missing')
  fields,form=drupal_form(matches[0]);return form
 def autocomplete(path,term):return drupal_autocomplete(http.json(base+'/autocomplete/'+path+'?'+urllib.parse.urlencode({'q':term})))
 cities=[c for c in autocomplete('read_city',geo['settlement']) if city_key(c['name'])==city_key(geo['settlement'])]
 if len(cities)!=1:raise ValueError('official_city_not_unique')
 city=cities[0];selected={'search_type':'0','city':city['value'],'city_id':city['id'],'street':'','street_id':'','house':'','house_id':''};post(selected)
 inventory=state.setdefault('streetInventory',{})
 def search_streets(term):return [{'id':r['id'],'value':r['value']} for r in autocomplete('read_street/'+city['id'],term) if not r['name'].startswith('*.')]
 streets=search_inventory(search_streets,inventory,cap=10,initial_queries=['']+list('абвгґдеєжзиіїйклмнопрстуфхцчшщьюя'),max_queries=min(6,max(1,http.limit//10)))
 rows=[];observed=[];errors=[];completed=[];done=state.setdefault('checkedHouseIds',{});count=0
 for street in sorted(streets,key=lambda r:str(r['id'])):
  street_name=re.sub(r'^(вулиця|провулок)\.\s*',r'\1 ',street['value'],flags=re.I)
  selected.update(street=street['value'],street_id=street['id'],house='',house_id='')
  try:
   post(selected);hi=state.setdefault('houseInventories',{}).setdefault(str(street['id']),{})
   houses=search_inventory(lambda term:autocomplete('read_house/'+str(street['id']),term),hi,cap=10,initial_queries=['']+list('0123456789'),max_queries=3)
   for h in houses:
    if not house(h['value']):continue
    if str(h['id']) in done.get(str(street['id']),[]):continue
    raw_exact=autocomplete('read_house/'+str(street['id']),h['value'])
    exact=[r for r in raw_exact if house_key(r['value'])==house_key(h['value'])]
    if len(raw_exact)>=10 or len(exact)!=1:continue
    selected.update(house=h['value'],house_id=h['id']);post(selected);form=post(selected,True)
    if any(str(fields.get(key,''))!=str(selected[key]) for key in ('city_id','street_id','house_id')):raise ValueError('official_answer_does_not_echo_selected_address')
    q=drupal_queue(form);at=int(time.time()*1000)
    observed.append(observe(geo,street_name,h['value'],street['id']));done.setdefault(str(street['id']),[]).append(str(h['id']));count+=1
    if q:
     r=emitted('vinnytsia',geo,street_name,h['value'],q,base,at,city['id'],street['id'])
     if r:rows.append(r)
  except Exception as e:errors.append({'stage':'official_form','streetId':str(street['id']),'error':type(e).__name__,'httpStatus':getattr(e,'code',None)});break
 state.update(dictionaryComplete=False,crawlStatus='partial',inventoryPendingQueries=len(inventory.get('queries',[])))
 if not inventory.get('queries') and not inventory.get('unexpanded') and all(not hi.get('queries') and not hi.get('unexpanded') for hi in state.get('houseInventories',{}).values()):
  state.update(streetInventory={},houseInventories={},checkedHouseIds={})
 return rows,observed,completed,errors,{'sourceCityId':city['id'],'discoveredStreets':len(streets),'verifiedHouseFormResponses':count}


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--operator',required=True,choices=CONFIG);p.add_argument('--target-city',required=True);p.add_argument('--output',required=True);p.add_argument('--state');p.add_argument('--full-city',action='store_true');p.add_argument('--request-limit',type=request_limit,default=120);p.add_argument('--budget',type=int);p.add_argument('--street-limit',type=int);p.add_argument('--city-limit',type=int);args=p.parse_args()
 geo=geography(args.operator,args.target_city);path=Path(args.output);statefile=Path(args.state) if args.state else path.with_suffix('.state.json');saved=json.loads(statefile.read_text()) if statefile.exists() else {};state=scoped_state(saved,args.target_city,True);http=HTTP(args.request_limit);rows=[];observed=[];completed=[];errors=[];metadata={}
 try:
  if args.operator=='kirovohrad':rows,observed,completed,errors,metadata=kirovohrad(http,geo,state)
  elif args.operator=='volyn':rows,observed,completed,errors,metadata=volyn(http,geo,state)
  elif args.operator=='prykarpattia':rows,observed,completed,errors,metadata=prykarpattia(http,geo,state)
  elif args.operator=='vinnytsia':rows,observed,completed,errors,metadata=vinnytsia(http,geo,state)
  else:raise ValueError('public_geographic_address_inventory_required')
 except Exception as e:errors.append({'stage':'collection','error':type(e).__name__,'httpStatus':getattr(e,'code',None),'reason':str(e)[:180]})
 now=int(time.time()*1000);state['updatedAt']=now;path.parent.mkdir(parents=True,exist_ok=True);statefile.parent.mkdir(parents=True,exist_ok=True);temp=statefile.with_suffix('.tmp');temp.write_text(json.dumps(saved,ensure_ascii=False,indent=2)+'\n');temp.replace(statefile)
 report={'operatorId':args.operator,'checkedAt':now,'records':len(rows),'observedHouses':len(observed),'completedStreetIds':completed,'requests':http.trace,'errors':errors,'cityCrawl':{'targetCity':geo['settlement'],'mode':'resumable-official-city-form','status':state.get('crawlStatus','blocked'),'dictionaryComplete':state.get('dictionaryComplete',False),**metadata},'method':'source-derived public city dictionary; not independent Android UI coverage'}
 Path(str(path)+'.report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 if rows or observed:path.write_text(json.dumps({'schemaVersion':1,'operatorId':args.operator,'generatedAt':now,'expiresAt':max((r['expiresAt'] for r in rows),default=now+86400000),'records':rows,'observedHouses':observed,'completedStreetIds':completed},ensure_ascii=False,separators=(',',':'))+'\n')
 print(json.dumps({'operatorId':args.operator,'records':len(rows),'observedHouses':len(observed),'errors':len(errors)}))
 if not rows and not observed:raise SystemExit(2)
if __name__=='__main__':main()
