"""Expanded editor and map selection on the signed APK. QA GPS/state is external."""
import pathlib,json,copy,time,threading,xml.etree.ElementTree as E
prefix=pathlib.Path('candidate/settings-ui-smoke.py').read_text().split('\ntry:')[0]
c={'__name__':'editor_map_helpers'};exec(compile(prefix,'editor_map_helpers','exec'),c)
adb=c['adb'];xml=c['xml'];tap=c['tap'];wait=c['wait'];seed=c['seed'];launch=c['launch'];evidence=c['evidence'];out=c['out'];pkg=c['pkg'];source_wait=c['source_wait'];bounds=c['c']['bounds'];scroll=c['scroll'];flags={}
def positive(n):
 b=bounds(n);return len(b)==4 and b[2]>b[0] and b[3]-b[1]>30

def find(label):
 for _ in range(16):
  s=xml();tree=E.fromstring(s)
  nodes=[n for n in tree.iter('node') if label in [n.get('text'),n.get('content-desc'),n.get('resource-id','').split('/')[-1]] and positive(n)]
  if nodes:return s,nodes[0]
  scroll(tree)
 raise AssertionError('Editor field did not become visible without expanding a section: '+label)

def form_top():
 for _ in range(10):adb('shell','input','swipe','540','400','540','1500','180')
 time.sleep(.5)

def map_pin(s):
 tree=E.fromstring(s);pins=[n for n in tree.iter('node') if 'Позначка адреси' in (n.get('content-desc','')+' '+n.get('text','')) and positive(n)]
 assert pins,'Real map marker was not exposed by WebView';p=min(pins,key=lambda n:(bounds(n)[2]-bounds(n)[0])*(bounds(n)[3]-bounds(n)[1]));b=bounds(p)
 views=[bounds(n) for n in tree.iter('node') if n.get('class')=='android.webkit.WebView' and positive(n) and bounds(n)[0]<=b[0] and bounds(n)[1]<=b[1] and bounds(n)[2]>=b[2] and bounds(n)[3]>=b[3]];assert views,'Marker is not inside the map WebView';v=min(views,key=lambda b:(b[2]-b[0])*(b[3]-b[1]));x=(b[0]+b[2])/2;y=(b[1]+b[3])/2
 assert v[0]+.2*(v[2]-v[0])<x<v[0]+.8*(v[2]-v[0]) and v[1]+.2*(v[3]-v[1])<y<v[1]+.8*(v[3]-v[1]),'Initial pin is not near map centre'

stop=threading.Event();thread=None
try:
 state=json.loads(pathlib.Path('candidate/fixture.json').read_text());p=state['places'][0];p.update(name='QA Address',queue='3.1',queueOrigin='manual',queueConfirmed=True,coordinateAccuracy='house',addressParts={'settlement':'Попівка','street':'провулок Романенка','house':'2а'});state.update(activePlaceId=p['id'],snapshots={})
 seed(state)
 for permission in ['android.permission.ACCESS_FINE_LOCATION','android.permission.ACCESS_COARSE_LOCATION']:adb('shell','pm','revoke',pkg,permission,check=False)
 launch();source_wait('Редагувати адресу');tap('Редагувати адресу');s=wait('Налаштування адреси','use-current-position','open-address-map');tree=E.fromstring(s)
 for id in ['use-current-position','open-address-map']:
  button=next(n for n in tree.iter('node') if n.get('resource-id','').split('/')[-1]==id);assert button.get('class')=='android.widget.Button' and positive(button)
 flags['neutralTitleAndActionButtons']=True;evidence('editor-expanded-top',s)
 for label in ['Область','Район','Населений пункт','Вулиця','Будинок']:find('Обрати: '+label)
 flags['postalFieldsInitiallyExpanded']=True
 find('Назва адреси · необов’язково');s,_=find('Оператор розподілу')
 if not any(n.get('checkable')=='true' for n in E.fromstring(s).iter('node')):scroll(E.fromstring(s));s=xml()
 assert any(n.get('checkable')=='true' for n in E.fromstring(s).iter('node'))
 s,_=find('Черга · якщо знаєте її номер');assert any(n.get('class')=='android.widget.EditText' and n.get('text')=='3.1' for n in E.fromstring(s).iter('node'));flags['nameOperatorQueueInitiallyVisible']=True;evidence('editor-expanded-data',s)
 find('connection-value');flags['connectionFormInitiallyVisible']=True
 s,button=find('delete-place');assert button.get('class')=='android.widget.Button';flags['deleteIsButton']=True;evidence('editor-delete-button',s)
 form_top();tap('Обрати на мапі');s=wait('Пошук адреси на мапі','Позначка адреси','Знайти адресу',p['address']);map_pin(s);flags['savedHousePinWithoutGPSPermission']=True;evidence('editor-saved-house-map',s)
 tap('Знайти адресу');wait('Налаштування адреси');tap('Закрити');source_wait('Черга 3.1','вказано вами');persisted=c['state_read']()['places'][0];assert persisted['address']==p['address'] and persisted['queue']=='3.1' and persisted['queueOrigin']=='manual' and persisted['latitude']==p['latitude'] and persisted['longitude']==p['longitude'];flags['unchangedMapPinPreservesAddressQueue']=True
 launch();wait('current-address-card');c['navigate']('＋ Додати адресу');wait('Налаштування адреси')
 for permission in ['android.permission.ACCESS_COARSE_LOCATION','android.permission.ACCESS_FINE_LOCATION']:adb('shell','pm','grant',pkg,permission)
 adb('shell','settings','put','secure','location_mode','3');adb('shell','cmd','location','set-location-enabled','true',check=False)
 gps={'latitude':p['latitude']+.02,'longitude':p['longitude']+.03}
 def publish_gps():
  for _ in range(15):
   if stop.is_set():break
   adb('emu','geo','fix',str(gps['longitude']),str(gps['latitude']),check=False);stop.wait(1)
 thread=threading.Thread(target=publish_gps,daemon=True);thread.start();tap('Обрати на мапі');s=wait('Пошук адреси на мапі','Поточна геопозиція','Позначка адреси','Знайти адресу');map_pin(s);stop.set();thread.join(timeout=5);flags['newAddressMapUsesCurrentGPS']=True;evidence('editor-new-address-gps-map',s)
 tap('Скасувати');s=wait('Налаштування адреси','Оберіть область');assert p['address'] not in s;flags['cancelMapKeepsNewDraftBlank']=True;evidence('editor-new-map-cancelled',s)
finally:
 stop.set()
 if thread:thread.join(timeout=5)
 (out/'editor-map-location.txt').write_text(adb('shell','dumpsys','location',check=False))
 result={'api':adb('shell','getprop','ro.build.version.sdk').strip(),'flags':flags,'apkSha256':c['c']['meta']['sha256'],'allPassed':len(flags)==9 and all(flags.values()),'scope':'Injected saved-house coordinates and Android emulator GPS; visible real WebView marker and GPS/address entry, generated map centre/zoom separately tested in JavaScript. Live tile coverage/house geocoder and physical GPS accuracy not asserted.'};(out/'editor-map-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print('EDITOR_MAP_RESULT',json.dumps(result),flush=True)
