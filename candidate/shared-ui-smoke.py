"""Shared controls: real taps, persisted edits and screenshot bounds. QA fixture only."""
import pathlib,json,copy,time,re,xml.etree.ElementTree as E
from PIL import Image
prefix=pathlib.Path('candidate/editor-map-smoke.py').read_text().split('\nstop=threading.Event()')[0]
c={'__name__':'shared_ui_helpers'};exec(compile(prefix,'shared_ui_helpers','exec'),c)
adb=c['adb'];xml=c['xml'];tap=c['tap'];wait=c['wait'];seed=c['seed'];launch=c['launch'];evidence=c['evidence'];find=c['find'];top=c['form_top'];bounds=c['bounds'];out=c['out'];hide_keyboard=c['hide_keyboard'];flags={}
def by_id(s,id):return next((n for n in E.fromstring(s).iter('node') if n.get('resource-id','').split('/')[-1]==id),None)
def full_row(id):
 for attempt in range(16):
  s=xml();node=by_id(s,id);viewport=by_id(s,'address-form');assert viewport is not None;v=bounds(viewport)
  b=bounds(node) if node is not None else []
  if len(b)==4 and b[0]<b[2] and v[1]+8<b[1]<b[3]<v[3]-8:return s,node
  # UIAutomator exposes partly clipped rows; inspect only after the entire row
  # is inside the real ScrollView viewport, clear of the sticky Save footer.
  x=(v[0]+v[2])//2;middle=(v[1]+v[3])//2;distance=min(350,(v[3]-v[1])//3)
  if len(b)==4 and b[2]>b[0] and b[3]>b[1] and b[1]<=v[1]+8:adb('shell','input','swipe',str(x),str(middle-distance//2),str(x),str(middle+distance//2),'250')
  else:adb('shell','input','swipe',str(x),str(middle+distance//2),str(x),str(middle-distance//2),'250')
  time.sleep(.7)
 raise AssertionError('Full row did not enter the viewport: '+id)
def saved():return c['c']['state_read']()['places'][0]
def arrow_pixels(id,s,name):
 node=by_id(s,id);assert node is not None and node.get('enabled')=='true';b=bounds(node);assert b[2]-b[0]>400
 evidence(name,s);im=Image.open(out/(name+'.png')).convert('RGB');points=[];white=[]
 for y in range(max(0,b[1]+3),min(im.height,b[3]-3)):
  for x in range(b[0]+3,min(im.width,b[2]-3)):
   r,g,blue=im.getpixel((x,y))
   if g>170 and blue>150 and r<170 and g>r+35:points.append((x,y))
   if min(r,g,blue)>185 and max(r,g,blue)-min(r,g,blue)<40:white.append((x,y))
 assert points and white,'Could not distinguish native text and chevron pixels'
 left=min(x for x,y in points);right=max(x for x,y in points)
 assert b[2]-115<left<right<b[2]-25,(id,b,left,right)
 assert max(x for x,y in white)<left-10,'Text overlaps the reserved chevron region'

original_font=adb('shell','settings','get','system','font_scale').strip()
try:
 state=json.loads(pathlib.Path('candidate/fixture.json').read_text());p=state['places'][0]
 long_name='Довга назва адреси для перевірки очищення всього тексту одним натисканням'
 p.update(name=long_name,queue='3.1',queueOrigin='manual',queueConfirmed=True,coordinateAccuracy='house',addressOrigin='postal',addressParts={'settlement':'Попівка','street':'провулок Романенка','house':'2а'},addressSelection={'region':{'id':'UA-71','name':'Черкаська область'},'district':{'id':'qa-district','label':'Дуже довга назва району для перевірки перенесення тексту без накладання на стрілку'},'city':{'id':'qa-city','name':'Населений пункт із дуже довгою назвою для перевірки правого краю'},'street':{'id':'qa-street','name':'Вулиця з дуже довгою назвою для перевірки перенесення в кілька рядків'},'house':{'id':'qa-house','name':'2а'}})
 state.update(places=[p],activePlaceId=p['id'],snapshots={})
 for font in ['1.0','1.5']:
  adb('shell','settings','put','system','font_scale',font);seed(copy.deepcopy(state));c['c']['source_wait']('Редагувати адресу');tap('Редагувати адресу');wait('Налаштування адреси')
  for level in ['region','district','city','street','house']:
   s,_=full_row('address-select-'+level);arrow_pixels('address-select-'+level,s,'shared-select-'+level+'-font-'+font)
  flags['selectArrowsAndLongTextFont'+font]=True
 adb('shell','settings','put','system','font_scale','1.0');seed(copy.deepcopy(state));c['c']['source_wait']('Редагувати адресу');tap('Редагувати адресу');wait('Налаштування адреси')
 s,node=full_row('address-name-input');assert node.get('text')==long_name;evidence('shared-name-before-clear',s)
 tap('address-name-input-clear');s=xml();assert by_id(s,'address-name-input').get('text','') in ['', 'Дім, робота, батьки…'];assert by_id(s,'address-name-input-clear') is None
 adb('shell','input','text','QA_Replacement');c['c']['c']['wait_edit']('QA_Replacement');hide_keyboard();evidence('shared-name-replaced',xml());tap('save-place');c['c']['top']();wait('current-address-card','QA_Replacement')
 actual=saved();assert actual['name']=='QA_Replacement' and actual['queue']=='3.1' and actual['queueOrigin']=='manual';launch();wait('current-address-card','QA_Replacement');flags['oneTapNameReplacementPersists']=True
 c['c']['source_wait']('Редагувати адресу');tap('Редагувати адресу');wait('Налаштування адреси');full_row('address-queue-input');tap('address-queue-input-clear');s=xml();assert by_id(s,'address-queue-input-clear') is None
 adb('shell','input','text','2.2');c['c']['c']['wait_edit']('2.2');hide_keyboard();tap('save-place');c['c']['source_wait']('Черга 2.2');actual=saved();assert actual['queue']=='2.2' and actual['queueOrigin']=='manual' and actual['name']=='QA_Replacement';flags['oneTapQueueReplacementPersists']=True
 launch();c['c']['source_wait']('Редагувати адресу');tap('Редагувати адресу');wait('Налаштування адреси');top();full_row('address-select-street');tap('Обрати: Вулиця');wait('address-search-input');tap('address-search-input');adb('shell','input','text','zzzzz');c['c']['c']['wait_edit']('zzzzz');evidence('shared-search-before-clear',xml());tap('address-search-input-clear');s=xml();assert by_id(s,'address-search-input-clear') is None;assert by_id(s,'address-search-input').get('text','') in ['', 'Пошук у списку'];hide_keyboard();tap('Закрити список адрес');wait('Налаштування адреси');assert not c['save_enabled'](xml());tap('Закрити');actual=saved();assert actual['queue']=='2.2' and actual['name']=='QA_Replacement';flags['searchClearAndCancelPreserveAddress']=True
finally:
 adb('shell','settings','put','system','font_scale',original_font,check=False)
 result={'api':adb('shell','getprop','ro.build.version.sdk').strip(),'apkSha256':c['c']['c']['meta']['sha256'],'flags':flags,'allPassed':len(flags)==5 and all(flags.values()),'scope':'External synthetic long labels, native text edits and screenshot pixel boundaries at fonts1/1.5. No synthetic addresses or lookup fixtures in APK; no live coverage claim.'};(out/'shared-ui-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print('SHARED_UI_RESULT',json.dumps(result),flush=True)
