"""Reference-focused visual acceptance of the actual APK. All fixtures are external.
Aurora Glass compares published81 and candidate82 on identical state.
Legacy Moss selection upgrades to Aurora Light; all captures are the signed APK.
"""
import pathlib,json,sqlite3,time,copy,datetime,zoneinfo,xml.etree.ElementTree as E,subprocess
from PIL import Image,ImageChops
prefix=pathlib.Path('candidate/editor-map-smoke.py').read_text().split('\nstop=threading.Event()')[0]
c={'__name__':'reference_helpers'};exec(compile(prefix,'reference_helpers','exec'),c)
adb=c['adb'];xml=c['xml'];tap=c['tap'];wait=c['wait'];launch=c['launch'];evidence=c['evidence'];out=c['out'];pkg=c['pkg'];top=c['c']['top'];source_wait=c['source_wait'];bounds=c['bounds'];meta=c['c']['c']['meta'];flags={};metrics={}
def node(s,id):return next((n for n in E.fromstring(s).iter('node') if n.get('resource-id','').split('/')[-1]==id),None)
def text_node(s,text):return next((n for n in E.fromstring(s).iter('node') if n.get('text')==text),None)
def pixels(image,box,fn):
 b=list(map(int,box));return sum(fn(image.getpixel((x,y))) for y in range(max(0,b[1]),min(image.height,b[3])) for x in range(max(0,b[0]),min(image.width,b[2])))
def screenshot(name):
 s=xml();evidence(name,s);return s,Image.open(out/(name+'.png')).convert('RGB')
def seed(state,theme):
 adb('shell','am','force-stop',pkg);adb('shell','pm','clear',pkg)
 if int(adb('shell','getprop','ro.build.version.sdk').strip())>=33:adb('shell','pm','grant',pkg,'android.permission.POST_NOTIFICATIONS')
 p=out/'reference-RKStorage';p.unlink(missing_ok=True)
 with sqlite3.connect(p) as db:
  db.execute('CREATE TABLE catalystLocalStorage(key TEXT PRIMARY KEY,value TEXT NOT NULL)');db.execute('PRAGMA user_version=1')
  db.execute('INSERT INTO catalystLocalStorage VALUES (?,?)',('svitlo.state.v1',json.dumps(state,ensure_ascii=False)))
  db.execute('INSERT INTO catalystLocalStorage VALUES (?,?)',('svitlo.appearance.v1',json.dumps({'version':1,'theme':theme})))
 remote=f'/data/data/{pkg}/databases';adb('shell','mkdir','-p',remote);adb('push',str(p),remote+'/RKStorage')
 uid=adb('shell','stat','-c','%u',f'/data/data/{pkg}').strip();assert uid.isdigit();adb('shell','chown','-R',f'{uid}:{uid}',remote);adb('shell','restorecon','-R',remote);launch()
def persisted():
 adb('shell','am','force-stop',pkg);p=out/'reference-persisted.db';p.unlink(missing_ok=True);adb('pull',f'/data/data/{pkg}/databases/RKStorage',str(p))
 with sqlite3.connect(p) as db:return {k:json.loads(v) for k,v in db.execute('SELECT key,value FROM catalystLocalStorage WHERE key IN (?,?)',('svitlo.state.v1','svitlo.appearance.v1'))}
def canvas(im):
 sample=[im.getpixel((10,y)) for y in range(80,160,10)];return sum(sum(v)/3 for v in sample)/len(sample)
try:
 adb('root',check=False);adb('wait-for-device');adb('shell','wm','size','1080x2340');adb('shell','wm','density','440');adb('shell','settings','put','system','font_scale','1.0')
 adb('shell','svc','wifi','disable');adb('shell','svc','data','disable')
 state=json.loads(pathlib.Path('candidate/fixture.json').read_text());p=state['places'][0]
 p.update(name='Дім',queue='3.1',queueOrigin='manual',queueConfirmed=True,addressOrigin='postal',coordinateAccuracy='house',addressParts={'settlement':'Попівка','street':'провулок Романенка','house':'2а'},addressSelection={'region':{'id':'UA-71'},'district':{'id':'qa-district','name':'Черкаський','label':'Черкаський'},'city':{'id':'qa-city','name':'Попівка'},'street':{'id':'qa-street','name':'провулок Романенка'},'house':{'id':'qa-house','name':'2а'}})
 stamp=int(adb('shell','date','+%s').strip());instant=datetime.datetime.fromtimestamp(stamp,datetime.timezone.utc);local=instant.astimezone(zoneinfo.ZoneInfo('Europe/Kyiv'));day=local.date();minute=local.hour*60+local.minute
 start=max(60,min(1260,(minute//60-1)*60));end=min(1380,max(start+60,(minute//60+2)*60))
 slots=[{'start':0,'end':start,'type':'NotPlanned'},{'start':start,'end':end,'type':'Definite'},{'start':end,'end':1440,'type':'NotPlanned'}]
 plans={key:{'operatorId':p['operatorId'],'queue':p['queue'],'status':'ready','date':(day+datetime.timedelta(days=offset)).isoformat(),'checkedAt':instant.isoformat(),'validUntil':(stamp+86400)*1000,'intervals':[],'slots':slots,'refreshError':{'status':'source_unavailable','attemptedAt':instant.isoformat()}} for key,offset in [('today',0),('tomorrow',1)]}
 state.update(activePlaceId=p['id'],snapshots={p['id']:plans},notificationsEnabled=False,gpsAsked=True)
 adb('install','-r','-g','--abi','x86_64','previous.apk');seed(copy.deepcopy(state),'aurora');wait('current-address-card','schedule-graph');tap('Завтра');time.sleep(1);before,old=screenshot('aurora-published-81')
 # Upgrade an installation whose existing persisted light ID is still moss.
 seed(copy.deepcopy(state),'moss');wait('current-address-card');adb('shell','am','force-stop',pkg);adb('install','-r','-g','--abi','x86_64','candidate/'+meta['fileName']);launch();wait('current-address-card','schedule-graph');_,im=screenshot('light-upgraded-from-moss');assert canvas(im)>180
 saved=persisted();assert saved['svitlo.appearance.v1']=={'version':1,'theme':'moss'};assert saved['svitlo.state.v1']['places'][0]['queue']=='3.1' and saved['svitlo.state.v1']['places'][0]['queueOrigin']=='manual';assert saved['svitlo.state.v1']['snapshots'][p['id']]['today']['slots']==slots;flags['legacyLightUpgradePreservesThemeAddressManualQueueAndCache']=True
 seed(copy.deepcopy(state),'aurora');wait('current-address-card','schedule-graph');tap('Завтра');time.sleep(1);after,new=screenshot('aurora-candidate');assert old.size==new.size and canvas(new)<85
 roi=(0,64,new.width,1600);diff=ImageChops.difference(old.crop(roi),new.crop(roi));changed=sum(max(pixel)>12 for pixel in diff.getdata());fraction=changed/(diff.width*diff.height)
 metrics['auroraChangedPixelFraction']=fraction;assert fraction<.005,('Dark theme changed',fraction);flags['darkMatchesPublishedAppearance']=True
 seed(copy.deepcopy(state),'moss');wait('current-address-card','schedule-graph');s,im=screenshot('light-reference-default');assert canvas(im)>180
 navy=lambda rgb:rgb[2]>rgb[0] and max(rgb)<120
 brand=text_node(s,'СВІТЛО');assert brand is not None;count=pixels(im,bounds(brand),navy);assert count>150;metrics['navyWordmarkPixels']=count;flags['navyWordmarkOnIcyCanvas']=True
 bell=node(s,'notification-entry-open');assert bell is not None;gold=lambda rgb:rgb[0]>110 and rgb[1]>65 and rgb[2]<100 and rgb[0]>rgb[1]+15
 count=pixels(im,bounds(bell),gold);assert count>60;metrics['goldBellPixels']=count;flags['goldBellTile']=True
 current=node(s,f'timeline-card-{start}-{end}');assert current is not None and current.get('selected')=='true';tap(f'timeline-card-{start}-{end}');s,im=screenshot('light-reference-main');current=node(s,f'timeline-card-{start}-{end}');assert current is not None
 b=bounds(current);scale=1080/393;area=(b[0]+60*scale,b[1]+5*scale,b[2]-35*scale,b[3]-5*scale)
 warm=lambda rgb:rgb[0]>rgb[2]+15 and rgb[1]>rgb[2]+8
 count=pixels(im,area,warm);assert count>300;metrics['amberCurrentSurfacePixels']=count
 badge=text_node(s,'ЗАРАЗ');assert badge is not None;assert pixels(im,bounds(badge),navy)>20;flags['amberCurrentIntervalWithReadableDarkBadge']=True
 card=node(s,'current-address-card');name=node(s,'current-address-name');assert name is not None and name.get('text')=='Дім' and bounds(name)[0]>bounds(card)[0]+100;flags['homeIconAndSharedCompactMetrics']=True
 source_wait('Редагувати адресу');s,im=screenshot('light-reference-source');edit=next(n for n in E.fromstring(s).iter('node') if n.get('content-desc')=='Редагувати адресу');assert pixels(im,bounds(edit),gold)>60;flags['goldEditAction']=True
 tap('Редагувати адресу',scroll=True);s=wait('Налаштування адреси');assert not c['save_enabled'](s);screenshot('light-reference-editor');flags['editorPreservesCleanSave']=True
 tap('Обрати: Вулиця',scroll=True);wait('address-search-input');screenshot('light-reference-search');adb('shell','input','keyevent','4');s=xml()
 if node(s,'address-search-input') is not None:tap('Закрити список адрес')
 wait('Налаштування адреси');c['form_top']();tap('Обрати на мапі');s=wait('Пошук адреси на мапі','Позначка адреси');c['map_pin'](s);screenshot('light-reference-map');tap('Скасувати');wait('Налаштування адреси');assert not c['save_enabled'](xml());tap('Закрити');top();wait('current-address-card');flags['searchAndMapRemainFunctional']=True
 tap('schedule-notification-action');wait('notification-settings-dialog');screenshot('light-reference-notifications');tap('close-notification-settings');wait('current-address-card');top();c['c']['navigate']('Налаштування');wait('appearance-section');tap('appearance-section');s=wait('theme-aurora','theme-moss');assert text_node(s,'Aurora Light') is not None and text_node(s,'Moss Studio') is None;screenshot('light-reference-settings');flags['onlyTwoThemesWithNewLightName']=True
 tap('theme-aurora');screenshot('aurora-settings-after-switch');tap('theme-moss');tap('Закрити');wait('current-address-card');launch();wait('current-address-card');_,im=screenshot('light-restored-after-reference');assert canvas(im)>180;flags['switchAndRestartRemainFunctional']=True
finally:
 result={'api':adb('shell','getprop','ro.build.version.sdk').strip(),'apkSha256':meta['sha256'],'flags':flags,'metrics':metrics,'allPassed':len(flags)==11 and all(flags.values()),'scope':'Actual signed APK; legacy Moss selection upgrade, preserved manual queue/cache, unchanged dark pixels against published81 on identical emulator/state, Aurora Light graph/editor/source/search/map/notifications/settings. Dynamic external QA intervals. Manual visual review against approved light board required before publication.'}
 (out/'reference-visual-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print('REFERENCE_VISUAL_RESULT',json.dumps(result),flush=True)
