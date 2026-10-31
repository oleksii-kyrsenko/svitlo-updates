"""Native display-name/update acceptance; external fixtures never enter the product."""
import pathlib,json,sqlite3,time,copy,datetime,zoneinfo,xml.etree.ElementTree as E
from PIL import Image,ImageChops
c={'__name__':'launcher_helpers'};exec(compile(pathlib.Path('candidate/apk-smoke.py').read_text().split('\nflags={}')[0],'launcher_helpers','exec'),c)
adb=c['adb'];xml=c['xml'];tap=c['tap'];wait=c['wait_for'];launch=c['launch'];evidence=c['evidence'];out=c['out'];pkg=c['pkg'];meta=c['meta'];bounds=c['bounds'];flags={};metrics={}
def seed(state,theme):
 adb('shell','am','force-stop',pkg);p=out/'launcher-RKStorage';p.unlink(missing_ok=True)
 with sqlite3.connect(p) as db:
  db.execute('CREATE TABLE catalystLocalStorage(key TEXT PRIMARY KEY,value TEXT NOT NULL)');db.execute('PRAGMA user_version=1')
  for k,v in [('svitlo.state.v1',state),('svitlo.appearance.v1',{'version':1,'theme':theme})]:db.execute('INSERT INTO catalystLocalStorage VALUES (?,?)',(k,json.dumps(v,ensure_ascii=False)))
 remote=f'/data/data/{pkg}/databases';adb('shell','mkdir','-p',remote);adb('push',str(p),remote+'/RKStorage');uid=adb('shell','stat','-c','%u',f'/data/data/{pkg}').strip();assert uid.isdigit();adb('shell','chown','-R',f'{uid}:{uid}',remote);adb('shell','restorecon','-R',remote)
def saved():
 adb('shell','am','force-stop',pkg);p=out/'saved.db';adb('pull',f'/data/data/{pkg}/databases/RKStorage',str(p))
 with sqlite3.connect(p) as db:return {k:json.loads(v) for k,v in db.execute('SELECT key,value FROM catalystLocalStorage WHERE key IN (?,?)',('svitlo.state.v1','svitlo.appearance.v1'))}
def icon_node(s):return next((n for n in E.fromstring(s).iter('node') if n.get('text')=='Коли світло' or n.get('content-desc')=='Коли світло'),None)
def by_id(s,id):return next((n for n in E.fromstring(s).iter('node') if n.get('resource-id','').split('/')[-1]==id),None)
def full_field(id):
 for attempt in range(14):
  s=xml();n=by_id(s,id)
  if n is not None:
   b=bounds(n)
   if b[2]>b[0] and 180<b[1]<b[3]<2120:return s
  c['scroll_down'](E.fromstring(s))
 raise AssertionError('Form field not visible: '+id)
def hide_keyboard():
 status=adb('shell','dumpsys','input_method')
 if 'mInputShown=true' in status or 'mIsInputViewShown=true' in status:
  adb('shell','input','keyevent','4');time.sleep(.5)
 # A stale platform IME flag must not accidentally discard the editor.
 s=xml()
 if by_id(s,'app-message-dialog') is not None:tap('Продовжити')
def dialog_capture(name,theme):
 s=wait('app-message-dialog');assert 'android:id/alertTitle' not in s;evidence(name,s)
 n=by_id(s,'app-message-dialog');b=bounds(n);im=Image.open(out/(name+'.png')).convert('RGB');pixels=[im.getpixel((x,y)) for y in range(max(0,b[1]+10),min(im.height,b[3]-10)) for x in range(max(0,b[0]+10),min(im.width,b[2]-10))]
 count=sum(blue>red+12 and blue>green for red,green,blue in pixels) if theme=='aurora' else sum(min(red,green,blue)>180 and blue>red+3 for red,green,blue in pixels)
 metrics[name+'ThemedPixels']=count;assert count>5000,(name,count)
def home_after_editor():
 wait('app-menu-button');c['top']();wait('current-address-card')
def replace_text(id,value):
 result=adb('shell','am','instrument','-w','-r','-e','resource',id,'-e','value',value,'ua.svitlo.qa.input/.InputBridge')
 assert 'inputResult=ok' in result and 'INSTRUMENTATION_CODE: -1' in result,result
 c['wait_edit'](value)
def popup_checks(theme):
 c['wait_source']('Редагувати адресу');tap('Редагувати адресу',scroll=True);wait('Налаштування адреси');full_field('address-name-input');replace_text('address-name-input','QA_Draft');hide_keyboard();tap('Закрити');wait('Залишити редагування?','app-message-dialog');dialog_capture('discard-dialog-'+theme,theme)
 tap('Продовжити');wait('Налаштування адреси');assert by_id(xml(),'address-name-input').get('text')=='QA_Draft';hide_keyboard();tap('Закрити');wait('app-message-dialog');adb('shell','input','keyevent','4');wait('Налаштування адреси');assert by_id(xml(),'app-message-dialog') is None and by_id(xml(),'address-name-input').get('text')=='QA_Draft'
 hide_keyboard();tap('Закрити');wait('app-message-dialog');tap('Відкинути зміни');home_after_editor();flags['themedConfirmationCancelBackAndDiscard']=True
 c['wait_source']('Редагувати адресу');tap('Редагувати адресу',scroll=True);wait('Налаштування адреси');full_field('address-queue-input');replace_text('address-queue-input','@@@');hide_keyboard();tap('save-place');wait('app-message-dialog','Перевірте номер черги');dialog_capture('validation-dialog-'+theme,theme);tap('Зрозуміло');wait('Налаштування адреси');assert by_id(xml(),'address-queue-input').get('text')=='@@@';hide_keyboard();tap('Закрити');wait('app-message-dialog');tap('Відкинути зміни');home_after_editor();flags['themedValidationPreservesDraftAndSavedQueue']=True
 c['wait_source']('Редагувати адресу');tap('Редагувати адресу',scroll=True);wait('Налаштування адреси');tap('Видалити адресу',scroll=True);s=wait('delete-place-dialog');assert 'android:id/alertTitle' not in s;evidence('delete-dialog-'+theme,s);tap('cancel-delete-place');wait('Налаштування адреси');tap('Закрити');home_after_editor();flags['existingDeleteDialogRetainsThemeAndCancel']=True
 current=saved();assert current['svitlo.state.v1']['places'][0]['name']==p['name'] and current['svitlo.state.v1']['places'][0]['queue']=='3.1';assert current['svitlo.appearance.v1']=={'version':1,'theme':savedTheme};launch();wait('current-address-card');flags['popupDecisionsDoNotChangeSavedAddressThemeOrQueue']=True
def appearance_check():
 c['top']();c['navigate']('Налаштування');wait('Вигляд');tap('Вигляд');s=wait('theme-aurora')
 assert by_id(s,'theme-moss') is None and 'Aurora Light' not in s and 'Moss Studio' not in s
 assert by_id(s,'theme-aurora').get('checked')=='true' or 'Aurora Glass' in s
 evidence('appearance-'+savedTheme,s);tap('Закрити');wait('current-address-card')
def graph(name):
 wait('current-address-card','schedule-graph');tap('Завтра');time.sleep(1);s=xml();evidence(name,s);return Image.open(out/(name+'.png')).convert('RGB')
def dark_difference(reference,current):
 roi=(0,200,current.width,1600);diff=ImageChops.difference(reference.crop(roi),current.crop(roi));return sum(max(v)>12 for v in diff.getdata())/(diff.width*diff.height)
try:
 adb('install','-r','candidate/qa-input-helper.apk');api=adb('shell','getprop','ro.build.version.sdk').strip()
 adb('shell','wm','size','1080x2340');adb('shell','wm','density','440');adb('shell','settings','put','system','font_scale','1.0');adb('shell','svc','wifi','disable');adb('shell','svc','data','disable')
 state=json.loads(pathlib.Path('candidate/fixture.json').read_text());p=state['places'][0];p.update(name='Дім',queue='3.1',queueOrigin='manual',queueConfirmed=True)
 stamp=int(adb('shell','date','+%s').strip());instant=datetime.datetime.fromtimestamp(stamp,datetime.timezone.utc);day=instant.astimezone(zoneinfo.ZoneInfo('Europe/Kyiv')).date()
 slots=[{'start':0,'end':600,'type':'NotPlanned'},{'start':600,'end':720,'type':'Definite'},{'start':720,'end':1440,'type':'NotPlanned'}]
 plans={key:{'operatorId':p['operatorId'],'queue':p['queue'],'status':'ready','date':(day+datetime.timedelta(days=offset)).isoformat(),'checkedAt':instant.isoformat(),'validUntil':(stamp+86400)*1000,'intervals':[],'slots':slots,'refreshError':{'status':'source_unavailable','attemptedAt':instant.isoformat()}} for key,offset in [('today',0),('tomorrow',1)]}
 state.update(activePlaceId=p['id'],snapshots={p['id']:plans},notificationsEnabled=False,gpsAsked=True)
 reference=None
 for savedTheme in ['aurora','moss']:
  # Reinstall baseline between independent update cases; downgrade is not used.
  adb('uninstall',pkg,check=False);adb('install','-g','--abi','x86_64','previous.apk');seed(copy.deepcopy(state),savedTheme);launch();baseline=graph('baseline-86-'+savedTheme)
  if savedTheme=='aurora':reference=baseline
  else:assert dark_difference(reference,baseline)>.05,'Baseline light fixture was not light'
  adb('shell','am','force-stop',pkg);adb('install','-r','-g','--abi','x86_64','candidate/'+meta['fileName']);launch();candidate=graph('upgraded-87-'+savedTheme)
  fraction=dark_difference(reference,candidate);metrics[savedTheme+'GraphChangedPixelFraction']=fraction;assert fraction<.005,(savedTheme,fraction)
  flags[savedTheme+'UpgradeUsesUnchangedAuroraGlass']=True
  appearance_check();current=saved();assert current['svitlo.appearance.v1']=={'version':1,'theme':savedTheme}
  v=current['svitlo.state.v1'];assert v['activePlaceId']==p['id'] and v['places'][0]['reminders']==p['reminders'] and v['notificationsEnabled']==state['notificationsEnabled'];assert v['places'][0]['id']==p['id'] and v['places'][0]['address']==p['address'] and v['places'][0]['queue']=='3.1' and v['places'][0]['queueOrigin']=='manual'
  for key in ['today','tomorrow']:
   assert v['snapshots'][p['id']][key]['slots']==slots and v['snapshots'][p['id']][key]['checkedAt']==plans[key]['checkedAt']
  flags[savedTheme+'AppearanceAddressManualQueueAndOfflineCachePreserved']=True
  launch();restarted=graph('restarted-87-'+savedTheme);assert dark_difference(reference,restarted)<.005;flags[savedTheme+'RestartRetainsDarkAppearanceAndCache']=True
 # Dialogs and editor still work for an installation whose persisted selection is light.
 popup_checks('aurora')
 c['wait_source']('Редагувати адресу');tap('Редагувати адресу',scroll=True);wait('Налаштування адреси');full_field('address-queue-input');replace_text('address-queue-input','2.2');hide_keyboard();tap('save-place');home_after_editor();c['wait_source']('Черга 2.2');evidence('manual-queue-saved',xml());current=saved();assert current['svitlo.state.v1']['places'][0]['queue']=='2.2' and current['svitlo.state.v1']['places'][0]['queueOrigin']=='manual';assert current['svitlo.appearance.v1']=={'version':1,'theme':'moss'};flags['ManualQueueEditWorksAfterLightFallback']=True
 adb('shell','pm','clear',pkg);launch();s=wait('Ввести адресу');evidence('clean-start-87',s);savedTheme='clean';appearance_check();flags['CleanStartOffersOnlyAuroraGlass']=True
finally:
 result={'api':adb('shell','getprop','ro.build.version.sdk').strip(),'apkSha256':meta['sha256'],'flags':flags,'metrics':metrics,'allPassed':len(flags)==12 and all(flags.values()),'scope':'Exact signed APK86→87 upgrade on both saved theme IDs; Aurora Glass rendering matches86 dark baseline, light option hidden, original appearance key retained, address/manual queue/offline cache and timestamps survive restart. Themed confirmation/validation/delete actions and manual queue editing checked; clean launch. External emulator fixtures and QA input helper only.'};(out/'theme-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print('THEME_RESULT',json.dumps(result),flush=True)
