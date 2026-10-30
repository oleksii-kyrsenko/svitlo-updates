"""Real app-wide theme switch, native screens, persistence and unchanged offline data.
All addresses/schedules below are external synthetic QA state, never part of APK.
"""
import pathlib,json,copy,time,sqlite3,datetime,zoneinfo,xml.etree.ElementTree as E
from PIL import Image
prefix=pathlib.Path('candidate/editor-map-smoke.py').read_text().split('\nstop=threading.Event()')[0]
c={'__name__':'themes_helpers'};exec(compile(prefix,'themes_helpers','exec'),c)
adb=c['adb'];xml=c['xml'];tap=c['tap'];wait=c['wait'];seed=c['seed'];launch=c['launch'];evidence=c['evidence'];out=c['out'];pkg=c['pkg'];top=c['c']['top'];source_wait=c['source_wait'];flags={}
def by_id(s,id):return next((n for n in E.fromstring(s).iter('node') if n.get('resource-id','').split('/')[-1]==id),None)
def snap(name,light):
 s=xml();evidence(name,s);im=Image.open(out/(name+'.png')).convert('RGB')
 # Sample the clear header margin, away from cards, map tiles and the system IME.
 # Keyboard colours may lag the app theme; they are not application-canvas pixels.
 points=[im.getpixel((10,y)) for y in range(80,160,10)]
 mean=sum(sum(p)/3 for p in points)/len(points)
 threshold=100 if 'dialog' in name else 180
 assert mean>threshold if light else mean<85,(name,mean)
 return s

def db_read():
 adb('shell','am','force-stop',pkg);p=out/'theme-state.db';p.unlink(missing_ok=True);adb('pull',f'/data/data/{pkg}/databases/RKStorage',str(p))
 with sqlite3.connect(p) as db:return {k:json.loads(v) for k,v in db.execute('SELECT key,value FROM catalystLocalStorage WHERE key IN (?,?)',('svitlo.state.v1','svitlo.appearance.v1'))}

def select(id):
 top();c['c']['navigate']('Налаштування');tap('appearance-section');s=wait('theme-aurora','theme-moss');tap('theme-'+id,scroll=True);s=wait('theme-'+id)
 node=by_id(s,'theme-'+id);assert node is not None and node.get('checked')=='true',(id,s)
 snap('theme-'+id+'-settings',id=='moss');tap('Закрити');wait('current-address-card')

def check_data(actual,expected):
 assert actual['activePlaceId']==expected['activePlaceId']
 assert [(p['id'],p['name'],p['queue'],p['queueOrigin']) for p in actual['places']]==[(p['id'],p['name'],p['queue'],p['queueOrigin']) for p in expected['places']]
 for key in ['today','tomorrow']:
  for field in ['date','checkedAt','validUntil','slots']:
   assert actual['snapshots'][expected['activePlaceId']][key][field]==expected['snapshots'][expected['activePlaceId']][key][field],(key,field)

original_font=adb('shell','settings','get','system','font_scale').strip()
try:
 adb('shell','svc','wifi','disable');adb('shell','svc','data','disable');adb('shell','settings','put','system','font_scale','1.0')
 state=json.loads(pathlib.Path('candidate/fixture.json').read_text());p=state['places'][0]
 p.update(name='QA Home',queue='3.1',queueOrigin='manual',queueConfirmed=True,addressOrigin='postal',coordinateAccuracy='house',addressParts={'settlement':'Попівка','street':'провулок Романенка','house':'2а'},addressSelection={'region':{'id':'UA-71'},'district':{'id':'qa-district','name':'Черкаський','label':'Черкаський'},'city':{'id':'qa-city','name':'Попівка'},'street':{'id':'qa-street','name':'провулок Романенка'},'house':{'id':'qa-house','name':'2а'}})
 second=copy.deepcopy(p);second.update(id='qa-theme-work',name='QA Work')
 stamp=int(adb('shell','date','+%s').strip());now=datetime.datetime.fromtimestamp(stamp,datetime.timezone.utc);day=now.astimezone(zoneinfo.ZoneInfo('Europe/Kyiv')).date()
 plans={k:{'operatorId':p['operatorId'],'queue':p['queue'],'status':'ready','date':(day+datetime.timedelta(days=offset)).isoformat(),'checkedAt':now.isoformat(),'validUntil':(stamp+86400)*1000,'intervals':[],'slots':[{'start':0,'end':600,'type':'NotPlanned'},{'start':600,'end':720,'type':'Definite'},{'start':720,'end':960,'type':'Possible'},{'start':960,'end':1440,'type':'NotPlanned'}]} for k,offset in [('today',0),('tomorrow',1)]}
 state.update(places=[p,second],activePlaceId=p['id'],snapshots={p['id']:plans},notificationsEnabled=False,gpsAsked=True)
 seed(copy.deepcopy(state));wait('current-address-card','schedule-graph');snap('theme-default-aurora-graph',False);flags['defaultAuroraNative']=True
 tap('Завтра');expected_date=(day+datetime.timedelta(days=1)).strftime('%d').lstrip('0');before=by_id(xml(),'schedule-date').get('text');assert before.startswith(expected_date+' ')
 for id,light in [('moss',True),('aurora',False)]:
  select(id);s=snap('theme-'+id+'-graph',light);assert by_id(s,'schedule-date').get('text')==before;assert 'ui-loader' not in s;flags[id+'PreservesSelectedDayAndNoBackgroundLoader']=True
  tap('schedule-notification-action');wait('notification-settings-dialog');snap('theme-'+id+'-notification-dialog',light);tap('close-notification-settings');wait('current-address-card');flags[id+'NotificationDialog']=True
  source_wait('Редагувати адресу');tap('Редагувати адресу');s=wait('Налаштування адреси','address-form');assert by_id(s,'save-place').get('enabled')=='false';snap('theme-'+id+'-editor',light);flags[id+'EditorRemainsClean']=True
  tap('Обрати: Вулиця',scroll=True);wait('address-search-input');snap('theme-'+id+'-search',light);adb('shell','input','keyevent','4');s=xml()
  # Close only if Android Back hid the IME instead of closing the modal.
  if by_id(s,'address-search-input') is not None:tap('Закрити список адрес')
  wait('Налаштування адреси');c['form_top']();tap('Обрати на мапі');s=wait('Пошук адреси на мапі','Позначка адреси');c['map_pin'](s);snap('theme-'+id+'-map',light);tap('Скасувати');wait('Налаштування адреси');flags[id+'SearchAndSavedPin']=True
  tap('Видалити адресу',scroll=True);wait('delete-place-dialog');snap('theme-'+id+'-delete-dialog',light);tap('Скасувати');assert not c['save_enabled'](xml());tap('Закрити');top();wait('current-address-card');flags[id+'DeleteCancelDoesNotDirty']=True
  current=db_read();assert current['svitlo.appearance.v1']=={'version':1,'theme':id};check_data(current['svitlo.state.v1'],state);launch();wait('current-address-card','schedule-graph');snap('theme-'+id+'-after-restart',light);flags[id+'PersistsWithoutChangingOfflineData']=True
  # App restart restores today's default independently of appearance.
  tap('Завтра');before=by_id(xml(),'schedule-date').get('text')
 # Large text and a long label in the light theme, same shared field and right chevron.
 select('moss');adb('shell','settings','put','system','font_scale','1.5');launch();wait('current-address-card');source_wait('Редагувати адресу');tap('Редагувати адресу');wait('Налаштування адреси');s,_=c['find']('Обрати: Область');snap('theme-moss-large-font-editor',True);assert not c['save_enabled'](s);flags['mossLargeFontEditor']=True
finally:
 adb('shell','settings','put','system','font_scale',original_font,check=False)
 result={'api':adb('shell','getprop','ro.build.version.sdk').strip(),'apkSha256':c['c']['c']['meta']['sha256'],'flags':flags,'allPassed':len(flags)==14 and all(flags.values()),'scope':'Two themes in real native APK: settings, graph, notification/deletion dialogs, editor/search/map, clean Save, restart persistence and unchanged offline plans; synthetic external state. Reduced-motion/background lifecycle additionally checked in React.'}
 (out/'themes-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print('THEMES_RESULT',json.dumps(result),flush=True)
