"""External street-consent controls: literal house, scoped UI and saved marker."""
import json,math,re,unicodedata,urllib.parse,xml.etree.ElementTree as ET
PREFIX='confirm-source-street-'
WARNING='Назви можуть відрізнятися. Перевірте повну адресу в джерелі оператора.'
SELECTION_MESSAGES={'Назва вулиці в оператора відрізняється. Перевірте повну адресу та підтвердьте відповідний запис.','Перевірте повну адресу та оберіть відповідний запис вулиці оператора.','Будинок знайдено в кількох записах вулиці. Уточніть адресу оператора.'}
CASES=[{'api':30,'caseId':'UA-46-capital-2'},{'api':35,'caseId':'UA-61-capital-1'},{'api':36,'caseId':'UA-21-capital-1'}]
SAMPLE_SHA='369aa30d4e4ec1f502b4d996f53b4555df953682ef4bf0449198d7c6eca97043'
def normalized(value):return ' '.join(unicodedata.normalize('NFKC','' if value is None else str(value)).casefold().split())
def house(value):
 value=re.sub(r'[\s№]','',normalized(value)).translate(str.maketrans('aceopx','асеорх'))
 return re.sub(r'(\d)[‐‑‒–—-](?=[а-яіїєґ]$)',r'\1',value)
def house_component(label):
 value=str(label).split(',')[-1].strip().rstrip('.')
 return house(re.sub(r'^(?:будинок|буд\.?|д\.?|№)\s*','',value,flags=re.I))
def words(value):
 value=re.sub(r'\([^)]*\)',' ',normalized(value));value=re.sub(r'(?<!\w)(?:вулиця|вул\.?)(?!\w)',' ',value)
 return ' '.join(re.findall(r'[^\W_]+',re.sub(r"[’'`ʼ]",'',value),re.U))
def locality(value):
 value=normalized(value);value=re.sub(r'^(?:м\.|с\.|г\.)\s*','',value)
 value=re.sub(r'^(?:с-ще|с\s*[-–]\s*ще|смт\.?|селище міського типу)\s+','',value)
 value=re.sub(r'\([^)]*\)',' ',value);value=re.sub(r"[’'`ʼ]",'',value)
 value=re.sub(r'(?<!\w)(?:м\.|с\.|смт\.?|місто|село|селище)(?!\w)',' ',value)
 return ' '.join(re.findall(r'[^\W_]+',value,re.U))
def katottg(value):
 if value is None or value=='':return ''
 if not isinstance(value,str):raise ValueError('Invalid string KATOTTG context')
 match=re.fullmatch(r'(?:UA)?([0-9]{17})',value.strip())
 if not match:raise ValueError('Invalid string KATOTTG context')
 return 'UA'+match[1]
def source_street(label):
 parts=[part.strip() for part in label.split(',')]
 if len(parts)<3:raise ValueError('Source choice lacks literal locality/street/house components')
 return parts[-2]
def identity(node):return node.get('resource-id','').split(':id/',1)[-1]
def bounds(node):
 m=re.fullmatch(r'\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]',node.get('bounds',''));b=tuple(map(int,m.groups())) if m else None
 return b if b and b[2]>b[0] and b[3]>b[1] else None
def contains(a,b):return bool(a and b and a[0]<=b[0]<b[2]<=a[2] and a[1]<=b[1]<b[3]<=a[3])
def editor(xml,width,height):
 root=ET.fromstring(xml);parents={c:p for p in root.iter() for c in p}
 def ancestors(node):
  result=[]
  while node in parents:node=parents[node];result.append(node)
  return result
 def shown(node):return not any(n.get('displayed')=='false' or n.get('visible-to-user')=='false' for n in [node,*ancestors(node)])
 forms=[n for n in root.iter() if identity(n)=='address-form' and shown(n)]
 if len(forms)!=1:raise ValueError('One active ordinary address form is required')
 form=forms[0];viewport=bounds(form);nodes=[n for n in root.iter() if n is form or form in ancestors(n)]
 visible=[n for n in nodes if shown(n) and contains(viewport,bounds(n)) and contains((0,0,width,height),bounds(n))]
 return nodes,visible,viewport,parents,form
def choices(xml,width,height):
 nodes,_,_,_,_=editor(xml,width,height);result={}
 for node in nodes:
  key=identity(node)
  if key.startswith(PREFIX):
   label=node.get('content-desc') or node.get('text') or ' '.join(n.get('text','') for n in node.iter()).strip()
   if key in result and result[key]!=label:raise ValueError('Duplicate source button identity has different literal labels')
   result[key]=label
 return result
def frame_signature(xml,width,height):
 _,visible,_,_,_=editor(xml,width,height)
 return json.dumps([(identity(n),n.get('text'),n.get('content-desc'),bounds(n)) for n in visible],ensure_ascii=False)
def home_top_visible(xml,width,height):
 root=ET.fromstring(xml);parents={c:p for p in root.iter() for c in p}
 def ancestors(node):
  result=[]
  while node in parents:node=parents[node];result.append(node)
  return result
 scrolls=[n for n in root.iter() if identity(n)=='main-scroll'];cards=[n for n in root.iter() if identity(n)=='current-address-card']
 if len(scrolls)!=1 or len(cards)!=1:return False
 scroll,card=scrolls[0],cards[0];chain=[card,*ancestors(card)]
 return bool(scroll in chain and not any(n.get('displayed')=='false' or n.get('visible-to-user')=='false' for n in chain) and contains(bounds(scroll),bounds(card)) and contains((0,0,width,height),bounds(card)))
def visible_choice(xml,key,exact_house,width,height):
 all_choices=choices(xml,width,height)
 if set(all_choices)!={key}:raise ValueError('Source choice must be globally unique in the active form')
 label=all_choices[key]
 if house_component(label)!=house(exact_house):raise ValueError('Source choice last address component differs from the frozen literal house')
 source_street(label);_,visible,viewport,parents,form=editor(xml,width,height)
 buttons=[n for n in visible if identity(n)==key and n.get('enabled')!='false']
 if len(buttons)!=1:raise ValueError('Unique source button is not fully visible and enabled')
 button=bounds(buttons[0]);warnings=[n for n in visible if normalized(n.get('text',''))==normalized(WARNING) and bounds(n)[3]<=button[1]+4 and 0<=button[1]-bounds(n)[3]<=160 and max(bounds(n)[0],button[0])<min(bounds(n)[2],button[2])]
 if len(warnings)!=1:raise ValueError('Source warning is not scoped next to this visible form button')
 ancestors=[];ancestor=buttons[0]
 while ancestor in parents:ancestor=parents[ancestor];ancestors.append(ancestor)
 row=next((n for n in ancestors if n is not form and warnings[0] in list(n.iter())),None)
 if row is None and not(parents.get(buttons[0]) is form and parents.get(warnings[0]) is form):raise ValueError('Warning and source button do not share a source row/card')
 status=[n.get('text') for n in visible if n.get('text') in SELECTION_MESSAGES]
 if not status:raise ValueError('Visible source status is not needs_selection before choice')
 if any(re.match(r'^(?:Черга|Ймовірна черга)\s+[\d.]+\s*·',n.get('text','')) for n in visible):raise ValueError('A queue is already presented as resolved before explicit source consent')
 return {'binding':'visible-address-form-source-warning-and-button','observedSelectionStatus':'needs_selection','selectionStatusTexts':status,'rowBinding':'common-source-row' if row is not None else 'contained-form-sibling-row','buttonId':key,'sourceLabel':label,'sourceStreet':source_street(label),'sourceHouse':house_component(label),'buttonBounds':button,'warningBounds':bounds(warnings[0]),'viewport':viewport}
def visible_selected_queue(xml,width,height):
 _,visible,_,_,_=editor(xml,width,height);pattern=re.compile(r'^Черга\s+([1-9]\d{0,2}(?:\.\d{1,2})?)\s*·\s*за вибраним вами записом оператора$');found=[]
 for n in visible:
  match=pattern.fullmatch(' '.join(n.get('text','').split()))
  if match:found.append(match[1])
 return found[0] if len(found)==1 else None
def same_value(a,b):return json.dumps(a,sort_keys=True,ensure_ascii=False,allow_nan=False)==json.dumps(b,sort_keys=True,ensure_ascii=False,allow_nan=False)
def validate_marker(place,case,choice,clock_window,expected_marker=None):
 marker=place.get('queueStreetSelection') or {};source=marker.get('source') or {};stamp=marker.get('selectedAt')
 if marker.get('version')!=1 or isinstance(stamp,bool) or not isinstance(stamp,(int,float)) or not math.isfinite(stamp) or not clock_window[0]<=stamp<=clock_window[1]:raise ValueError('Explicit consent marker timestamp is outside the measured Android click window')
 address=json.loads(marker.get('addressIdentity','null'));parts=place.get('addressParts') or {};context=place.get('addressContext') or {};street=(place.get('addressSelection') or {}).get('street') or {}
 expected=[place.get('operatorId') or '',place.get('regionId') or context.get('regionId') or '',locality(parts.get('settlement','')),locality(context.get('community','')),locality(context.get('district','')),katottg(context.get('katottg')),street.get('id') or '',words(parts.get('street','')),house(parts.get('house','')),place.get('connectionRevision') or '']
 if address!=expected:raise ValueError('Marker is not bound to the saved operator/geography/postal street/exact house/connection revision')
 if locality(parts.get('settlement',''))!=locality(case['city']) or house(parts.get('house',''))!=house(case['exactHouse']):raise ValueError('Marker locality/street/house differs from the frozen postal address')
 if house_component(choice['sourceLabel'])!=house(case['exactHouse']) or source.get('street')!=choice['sourceStreet']:raise ValueError('Marker literal source street/house differs from the actually clicked source choice')
 suffix=choice['buttonId'][len(PREFIX):];reference=source.get('id','')
 if not isinstance(reference,str) or not(reference==suffix or reference.endswith('|'+suffix)):raise ValueError('Saved source reference differs from the actual source button identity')
 if source.get('providerCityId') is not None and source.get('providerCityId')!=place.get('providerCityId'):raise ValueError('Saved source provider city differs from the final source identity')
 routing=[place.get('officialCityId'),place.get('dynamicStreetId')]
 if place.get('providerStreetId'):routing.append('provider:'+place['providerStreetId'])
 if suffix not in routing:raise ValueError('Clicked source identity differs from saved provider routing')
 url=urllib.parse.urlsplit(source.get('sourceUrl',''))
 if url.scheme!='https' or not url.netloc or url.username or url.password:raise ValueError('Literal public source URL is missing')
 if expected_marker is not None and not same_value(marker,expected_marker):raise ValueError('Offline restart changed the original explicit selection marker')
 return marker
def validate_ready(place,case,choice,clock_window,visible_queue):
 marker=validate_marker(place,case,choice,clock_window)
 if place.get('queueOrigin')!='official' or place.get('queueConfirmed') is not True or place.get('queueStreetResolution')!='user_selected' or place.get('queueStreetSelectedAt')!=marker['selectedAt'] or not place.get('queue') or place.get('queue')!=visible_queue:raise ValueError('Saved queue did not preserve official provenance and the explicit source-street resolution')
 if place.get('queueSource')!=marker['source']['sourceUrl']:raise ValueError('Final queue source differs from the explicitly chosen literal source')
 if place.get('officialAddress') and house_component(place['officialAddress'])!=house(case['exactHouse']):raise ValueError('Final provider address has another literal house')
 return marker
PLACE_FIELDS=['id','address','addressOrigin','addressParts','addressSelection','addressContext','regionId','operatorId','officialAddress','officialCityId','providerCityId','providerStreetId','dynamicCityId','dynamicStreetId','connectionRevision','queue','queueOrigin','queueConfirmed','queueStreetResolution','queueStreetSelectedAt','queueStreetSelection','queueCheckedAt','queueCheckStatus','queueCheckMessage','queueSource','queueAdapter','queueEvidence','queueTransport','reminders']
def projected(state,appearance):
 place=next((p for p in state.get('places',[]) if p.get('id')==state.get('activePlaceId')),None)
 return {'activePlaceId':state.get('activePlaceId'),'place':{k:place.get(k) for k in PLACE_FIELDS} if place else None,'settings':{k:state.get(k) for k in ['notificationsEnabled','gpsAsked','endpoint']},'appearance':appearance,'cache':state.get('snapshots',{}).get(place['id']) if place else None}
def unchanged_saved(before,after):
 for key in ['activePlaceId','settings','appearance']:
  if not same_value(before[key],after[key]):raise ValueError('Restart changed saved UUID/settings/appearance: '+key)
 for key in ['id','address','addressOrigin','addressParts','addressSelection','addressContext','regionId','operatorId','officialAddress','officialCityId','providerCityId','providerStreetId','dynamicCityId','dynamicStreetId','connectionRevision','queue','queueOrigin','queueConfirmed','queueStreetResolution','queueStreetSelectedAt','queueStreetSelection','queueCheckedAt','queueSource','queueAdapter','queueEvidence','queueTransport','reminders']:
  if not same_value(before['place'][key],after['place'][key]):raise ValueError('Offline restart changed saved consent/address field: '+key)
def unchanged_ready_cache(before,after):
 preserved=[]
 for day,snapshot in (before or {}).items():
  if snapshot.get('status') not in ['ready','emergency']:continue
  original={k:v for k,v in snapshot.items() if k!='refreshError'};current={k:v for k,v in ((after or {}).get(day) or {}).items() if k!='refreshError'}
  if not same_value(original,current):raise ValueError('Offline restart changed an original ready schedule cache: '+day)
  preserved.append(day)
 return {'readyDaysPreserved':preserved,'status':'PASS' if preserved else 'NOT_PRESENT','interpretation':'No schedule data is seeded; a missing ready cache is not claimed as a cache preservation success.'}
