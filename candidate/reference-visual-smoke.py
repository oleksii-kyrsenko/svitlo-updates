"""Reference-focused visual acceptance of the actual APK. All fixtures are external.
Moss compares identical state on published78 and candidate80 on one emulator.
Aurora checks the approved material/accent hierarchy and captures actual screens.
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
 start=max(60,min(1260,(minute//60-1)*60));end=min(1380,max(start+60,(minute//60+1)*60))
 slots=[{'start':0,'end':start,'type':'NotPlanned'},{'start':start,'end':end,'type':'Definite'},{'start':end,'end':1440,'type':'NotPlanned'}]
 plans={key:{'operatorId':p['operatorId'],'queue':p['queue'],'status':'ready','date':(day+datetime.timedelta(days=offset)).isoformat(),'checkedAt':instant.isoformat(),'validUntil':(stamp+86400)*1000,'intervals':[],'slots':slots,'refreshError':{'status':'source_unavailable','attemptedAt':instant.isoformat()}} for key,offset in [('today',0),('tomorrow',1)]}
 state.update(activePlaceId=p['id'],snapshots={p['id']:plans},notificationsEnabled=False,gpsAsked=True)
 # The baseline is the published signed APK; no rebuilt baseline or alternate renderer.
 adb('install','-r','-g','--abi','x86_64','previous.apk');seed(copy.deepcopy(state),'moss');wait('current-address-card','schedule-graph');tap('Завтра');time.sleep(1);before,old=screenshot('moss-published-78')
 adb('shell','am','force-stop',pkg);adb('install','-r','-g','--abi','x86_64','candidate/'+meta['fileName']);launch();wait('current-address-card','schedule-graph');tap('Завтра');time.sleep(1);after,new=screenshot('moss-candidate')
 assert old.size==new.size and canvas(new)>180
 # Exclude system clock/navigation and compare the stable app-owned graph region.
 roi=(0,64,new.width,1600);diff=ImageChops.difference(old.crop(roi),new.crop(roi));changed=sum(max(pixel)>12 for pixel in diff.getdata());fraction=changed/(diff.width*diff.height)
 metrics['mossChangedPixelFraction']=fraction;assert fraction<.005,('Moss changed',fraction);flags['mossMatchesPublishedAppearance']=True
 saved=persisted();assert saved['svitlo.appearance.v1']=={'version':1,'theme':'moss'};assert saved['svitlo.state.v1']['places'][0]['queue']=='3.1' and saved['svitlo.state.v1']['places'][0]['queueOrigin']=='manual';flags['upgradePreservesMossAndManualQueue']=True
 # Capture the corrected default theme, with a truthful cache warning retained.
 seed(copy.deepcopy(state),'aurora');wait('current-address-card','schedule-graph');s,im=screenshot('aurora-reference-default')
 assert canvas(im)<85;brand=text_node(s,'СВІТЛО');assert brand is not None;white=lambda rgb:min(rgb)>200 and max(rgb)-min(rgb)<30
 count=pixels(im,bounds(brand),white);assert count>150;metrics['whiteWordmarkPixels']=count;flags['whiteWordmark']=True
 bell=node(s,'notification-entry-open');assert bell is not None;gold=lambda rgb:rgb[0]>180 and rgb[1]>130 and rgb[2]<155 and rgb[0]>rgb[1]
 count=pixels(im,bounds(bell),gold);assert count>60;metrics['goldBellPixels']=count;flags['goldBellTile']=True
 current=node(s,f'timeline-card-{start}-{end}');assert current is not None and current.get('selected')=='true';tap(f'timeline-card-{start}-{end}');s,im=screenshot('aurora-reference-main')
 current=node(s,f'timeline-card-{start}-{end}');assert current is not None
 b=bounds(current);scale=1080/393;area=(b[0]+60*scale,b[1]+5*scale,b[2]-35*scale,b[3]-5*scale)
 warm=lambda rgb:rgb[0]>rgb[2]+8 and rgb[1]>rgb[2]+8
 warm_count=pixels(im,area,warm);assert warm_count>300;metrics['amberCurrentSurfacePixels']=warm_count;flags['amberCurrentIntervalAndFilledBolt']=True
 # Home glyph reserves its own space; the saved address still comes from state.
 card=node(s,'current-address-card');name=node(s,'current-address-name');assert name is not None and name.get('text')=='Дім' and bounds(name)[0]>bounds(card)[0]+100;flags['homeIconAndCompactCard']=True
 source_wait('Редагувати адресу');s,im=screenshot('aurora-reference-source');edit=next(n for n in E.fromstring(s).iter('node') if n.get('content-desc')=='Редагувати адресу');assert pixels(im,bounds(edit),gold)>60;flags['goldEditAction']=True
 tap('Редагувати адресу');s=wait('Налаштування адреси');assert not c['save_enabled'](s);screenshot('aurora-reference-editor');flags['editorPreservesCleanSave']=True
 tap('Обрати: Вулиця',scroll=True);wait('address-search-input');screenshot('aurora-reference-search');adb('shell','input','keyevent','4');s=xml()
 if node(s,'address-search-input') is not None:tap('Закрити список адрес')
 wait('Налаштування адреси');c['form_top']();tap('Обрати на мапі');s=wait('Пошук адреси на мапі','Позначка адреси');c['map_pin'](s);screenshot('aurora-reference-map');tap('Скасувати');wait('Налаштування адреси');assert not c['save_enabled'](xml());tap('Закрити');top();wait('current-address-card');flags['searchAndMapRemainFunctional']=True
 tap('schedule-notification-action');wait('notification-settings-dialog');screenshot('aurora-reference-notifications');tap('close-notification-settings');wait('current-address-card');top();c['c']['navigate']('Налаштування');wait('appearance-section');tap('appearance-section');wait('theme-aurora','theme-moss');screenshot('aurora-reference-settings');tap('theme-moss');screenshot('moss-settings-after-switch');tap('Закрити');wait('current-address-card');launch();wait('current-address-card');_,im=screenshot('moss-restored-after-reference');assert canvas(im)>180;flags['switchAndRestartRemainFunctional']=True
finally:
 result={'api':adb('shell','getprop','ro.build.version.sdk').strip(),'apkSha256':meta['sha256'],'flags':flags,'metrics':metrics,'allPassed':len(flags)==10 and all(flags.values()),'scope':'Actual signed candidate vs published78 Moss pixels on the same emulator/state; corrected Aurora wordmark/gold/amber/icon hierarchy and real graph/editor/source/search/map/notification/settings screenshots. Dynamic QA intervals follow the device clock. External data; visual match additionally requires human review against the approved board before publication.'}
 (out/'reference-visual-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print('REFERENCE_VISUAL_RESULT',json.dumps(result),flush=True)
