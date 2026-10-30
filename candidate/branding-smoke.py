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
 current=saved();assert current['svitlo.state.v1']['places'][0]['name']==p['name'] and current['svitlo.state.v1']['places'][0]['queue']=='3.1';assert current['svitlo.appearance.v1']=={'version':1,'theme':theme};launch();wait('current-address-card');flags['popupDecisionsDoNotChangeSavedAddressThemeOrQueue']=True
try:
 adb('install','-r','candidate/qa-input-helper.apk');api=adb('shell','getprop','ro.build.version.sdk').strip();theme='aurora' if api=='35' else 'moss'
 adb('shell','wm','size','1080x2340');adb('shell','wm','density','440');adb('shell','settings','put','system','font_scale','1.0');adb('shell','svc','wifi','disable');adb('shell','svc','data','disable')
 state=json.loads(pathlib.Path('candidate/fixture.json').read_text());p=state['places'][0];p.update(name='Дім',queue='3.1',queueOrigin='manual',queueConfirmed=True)
 stamp=int(adb('shell','date','+%s').strip());instant=datetime.datetime.fromtimestamp(stamp,datetime.timezone.utc);day=instant.astimezone(zoneinfo.ZoneInfo('Europe/Kyiv')).date()
 slots=[{'start':0,'end':600,'type':'NotPlanned'},{'start':600,'end':720,'type':'Definite'},{'start':720,'end':1440,'type':'NotPlanned'}]
 plans={key:{'operatorId':p['operatorId'],'queue':p['queue'],'status':'ready','date':(day+datetime.timedelta(days=offset)).isoformat(),'checkedAt':instant.isoformat(),'validUntil':(stamp+86400)*1000,'intervals':[],'slots':slots,'refreshError':{'status':'source_unavailable','attemptedAt':instant.isoformat()}} for key,offset in [('today',0),('tomorrow',1)]}
 state.update(activePlaceId=p['id'],snapshots={p['id']:plans},notificationsEnabled=False,gpsAsked=True)
 adb('install','-r','-g','--abi','x86_64','previous.apk');seed(state,theme);launch();wait('current-address-card','schedule-graph');tap('Завтра');time.sleep(1);evidence('graph-published-83',xml());old=Image.open(out/'graph-published-83.png').convert('RGB')
 adb('shell','am','force-stop',pkg);adb('install','-r','-g','--abi','x86_64','candidate/'+meta['fileName']);launch();wait('current-address-card','schedule-graph');tap('Завтра');time.sleep(1);evidence('graph-new-name',xml());new=Image.open(out/'graph-new-name.png').convert('RGB')
 roi=(0,200,new.width,1600);diff=ImageChops.difference(old.crop(roi),new.crop(roi));fraction=sum(max(v)>12 for v in diff.getdata())/(diff.width*diff.height);metrics.update(theme=theme,appGraphChangedPixelFraction=fraction);assert fraction<.005,('App graph changed',fraction);flags['graphBelowRenamedHeaderPreserved']=True
 # Both width and actual glyph area reserve the menu touch target.
 for font,density in [('1.0','440'),('1.5','540')]:
  adb('shell','wm','density',density);adb('shell','settings','put','system','font_scale',font);launch();s=wait('current-address-card','КОЛИ СВІТЛО');time.sleep(1);s=xml();tree=E.fromstring(s)
  word=next(n for n in tree.iter('node') if n.get('text')=='КОЛИ СВІТЛО');menu=next(n for n in tree.iter('node') if n.get('resource-id','').split('/')[-1]=='app-menu-button');a=bounds(word);b=bounds(menu);assert a[0]<a[2]<=b[0]-8 and b[2]>b[0],(a,b,font);evidence('wordmark-font-'+font,s)
 flags['newWordmarkFitsNormalAndNarrowLargeFont']=True
 adb('shell','wm','density','440');adb('shell','settings','put','system','font_scale','1.0');launch();wait('current-address-card');c['navigate']('Налаштування');wait('Про застосунок');tap('Про застосунок');s=wait('Коли світло допомагає стежити');evidence('new-name-about',s);flags['aboutUsesNewName']=True;tap('Закрити');wait('current-address-card')
 current=saved();assert current['svitlo.appearance.v1']=={'version':1,'theme':theme};v=current['svitlo.state.v1'];assert v['places'][0]['id']==p['id'] and v['places'][0]['queue']=='3.1' and v['places'][0]['queueOrigin']=='manual';assert v['snapshots'][p['id']]['tomorrow']['slots']==slots;flags['upgradePreservesAddressThemeManualQueueAndCache']=True
 launch();wait('current-address-card');popup_checks(theme)
 adb('shell','input','keyevent','3');time.sleep(2);adb('shell','input','swipe','540','2120','540','400','350');time.sleep(2)
 for attempt in range(7):
  s=xml();node=icon_node(s)
  if node is not None and bounds(node)[3]>bounds(node)[1]:break
  adb('shell','input','swipe','540','1900','540','500','350');time.sleep(1)
 else:raise AssertionError('Launcher did not show the application icon')
 evidence('launcher-drawer',s);im=Image.open(out/'launcher-drawer.png').convert('RGB');b=bounds(node);colors=[im.getpixel((x,y)) for y in range(max(0,b[1]),min(im.height,b[3])) for x in range(max(0,b[0]),min(im.width,b[2]))]
 cyan=sum(blue>120 and green>100 and red<green*.85 for red,green,blue in colors);gold=sum(red>170 and green>110 and blue<170 and red>blue+40 for red,green,blue in colors);metrics.update(launcherCyanPixels=cyan,launcherGoldPixels=gold);assert cyan>8 and gold>4,(b,cyan,gold);flags['renamedLauncherRetainsCyanBulbAndGoldBolt']=True
 adb('logcat','-c');tap('Коли світло');wait('current-address-card','schedule-graph');evidence('launched-by-icon',xml());flags['launcherIconOpensExistingApp']=True
 adb('shell','am','start','-W','-a','android.settings.APPLICATION_DETAILS_SETTINGS','-d','package:'+pkg);s=wait('Коли світло');evidence('system-app-info',s);flags['systemApplicationInfoShowsFullNewName']=True
finally:
 result={'api':adb('shell','getprop','ro.build.version.sdk').strip(),'apkSha256':meta['sha256'],'flags':flags,'metrics':metrics,'allPassed':len(flags)==11 and all(flags.values()),'scope':'App-owned confirmation/validation/delete dialogs use the active theme; Continue/Android Back preserve drafts and Discard drops only changes; invalid queue remains editable with saved state intact. Actual signed APK83→86 upgrade preserving identity/address/manual queue/theme/cache. Graph below renamed header unchanged; new wordmark at393dp/font1 and320dp/font1.5; renamed about screen, actual launcher label and lamp, tap to launch, full new Android app-info name. Aurora Glass on API35, Aurora Light on API30/36. External QA data and platform Accessibility ACTION_SET_TEXT helper only; helper is not part of the application APK.'};(out/'branding-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print('BRANDING_RESULT',json.dumps(result),flush=True)
