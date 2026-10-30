"""Saved-place lifecycle and app-wide settings in the exact signed APK; injected state is QA-only."""
import pathlib,json,sqlite3,time,re,copy,xml.etree.ElementTree as E
helpers=pathlib.Path('candidate/apk-smoke.py').read_text().split('flags={}')[0]
c={'__name__':'settings_helpers'};exec(compile(helpers,'settings_helpers','exec'),c)
adb=c['adb'];out=c['out'];pkg=c['pkg'];launch=c['launch'];wait=c['wait_for'];evidence=c['evidence'];tap=c['tap'];xml=c['xml'];scroll=c['scroll_down'];navigate=c['navigate'];source_wait=c['wait_source']
flags={}
def top():
 for _ in range(5):adb('shell','input','swipe','540','400','540','1500','250')
 time.sleep(1)
def state_read():
 adb('shell','am','force-stop',pkg);path=out/'settings-persisted.db';path.unlink(missing_ok=True);adb('pull',f'/data/data/{pkg}/databases/RKStorage',str(path))
 with sqlite3.connect(path) as db:return json.loads(db.execute('SELECT value FROM catalystLocalStorage WHERE key=?',('svitlo.state.v1',)).fetchone()[0])
def seed(state):
 adb('shell','am','force-stop',pkg);adb('shell','pm','clear',pkg)
 if int(adb('shell','getprop','ro.build.version.sdk').strip())>=33:adb('shell','pm','grant',pkg,'android.permission.POST_NOTIFICATIONS')
 local=out/'settings-RKStorage';local.unlink(missing_ok=True)
 with sqlite3.connect(local) as db:
  db.execute('CREATE TABLE catalystLocalStorage(key TEXT PRIMARY KEY,value TEXT NOT NULL)');db.execute('PRAGMA user_version=1');db.execute('INSERT INTO catalystLocalStorage VALUES (?,?)',('svitlo.state.v1',json.dumps(state,ensure_ascii=False)))
 remote=f'/data/data/{pkg}/databases';adb('shell','mkdir','-p',remote);adb('push',str(local),remote+'/RKStorage')
 uid=adb('shell','stat','-c','%u',f'/data/data/{pkg}').strip();assert uid.isdigit();adb('shell','chown','-R',f'{uid}:{uid}',remote);adb('shell','restorecon','-R',remote);launch()
def settings_action(label):
 tap(label,scroll=True)
 resumed=adb('shell','dumpsys','activity','activities')
 assert re.search(r'(?:mResumedActivity|topResumedActivity).*com.android.settings',resumed),resumed[-5000:]
 adb('shell','input','keyevent','4');wait('Налаштування')
try:
 adb('root',check=False);adb('wait-for-device')
 state=json.loads(pathlib.Path('candidate/fixture.json').read_text());base=state['places'][0];base.update(name='QA First',queueOrigin='manual',queueConfirmed=True)
 second=copy.deepcopy(base);second.update(id='qa-second',name='QA Second');third=copy.deepcopy(base);third.update(id='qa-third',name='QA Third');state.update(places=[base,second,third],activePlaceId=second['id'],snapshots={})
 seed(state);wait('current-address-card','QA Second');s=source_wait('Редагувати адресу');assert 'Змінити місце' not in s;flags['editLabelRenamed']=True
 top();navigate('Налаштування');s=wait('Дозволи та фонова робота','Вигляд','Про застосунок');tree=E.fromstring(s)
 assert 'QA Second' not in s and 'current-address-card' not in s and 'Нагадування для цієї адреси' not in s and 'Видалити адресу' not in s
 appearance=next(n for n in tree.iter('node') if n.get('resource-id','').split('/')[-1]=='appearance-section');assert appearance.get('enabled')=='true';tap('appearance-section');wait('Aurora Glass','Moss Studio');flags['settingsGlobalAndAppearanceWorks']=True;tap('appearance-section');evidence('settings-global',s)
 tap('Про застосунок');s=wait('Світло допомагає');assert 'плановими вимкненнями' in s;flags['aboutDescribesApp']=True;evidence('settings-about',s)
 top();tap('Дозволи та фонова робота');wait('Сповіщення Android:');settings_action('Налаштування сповіщень Android');flags['androidNotificationsAction']=True
 top();settings_action('Налаштування застосунку Android');flags['androidApplicationSettingsAction']=True
 top();s=xml()
 if 'Дозволити точні нагадування' in s:settings_action('Дозволити точні нагадування');flags['androidExactAlarmAction']=True
 else:assert int(adb('shell','getprop','ro.build.version.sdk').strip())<31 or 'Точні нагадування: дозволено' in s;flags['androidExactAlarmAction']=True
 top();tap('Увімкнути сповіщення та фонове оновлення',scroll=True);wait('Сповіщення ввімкнено');tap('OK');s=wait('Нагадування застосунку: увімкнено');flags['globalEnableWorks']=True;evidence('settings-permissions-enabled',s)
 top();tap('Закрити');wait('current-address-card','QA Second');source_wait('Редагувати адресу');tap('Редагувати адресу');tap('Видалити адресу',scroll=True);s=wait('Видалити адресу?','QA Second','cancel-delete-place');evidence('delete-confirmation',s)
 tap('Скасувати');s=wait('Налаштування адреси');assert 'delete-place-dialog' not in s;flags['deleteCancelStaysInEditor']=True
 tap('Видалити адресу',scroll=True);wait('delete-place-dialog');tap('confirm-delete-place');s=wait('current-address-card','QA First');assert 'Налаштування адреси' not in s;flags['deleteSelectsFirstRemaining']=True;evidence('delete-first-remaining',s)
 for expected in ['QA Third',None]:
  source_wait('Редагувати адресу');tap('Редагувати адресу');tap('Видалити адресу',scroll=True);wait('delete-place-dialog');tap('confirm-delete-place')
  if expected:wait('current-address-card',expected)
 s=wait('Налаштування адреси','Введіть адресу');assert 'delete-place' not in s;flags['lastDeletionOpensNewForm']=True;evidence('delete-last-add-form',s)
 persisted=state_read();assert persisted['places']==[] and persisted['activePlaceId'] is None and {base['id'],second['id'],third['id']}<=set(persisted['deleted']);flags['deletionsPersisted']=True
 # Settings are usable without an address, including before the first addition.
 seed({**state,'places':[],'activePlaceId':None,'deleted':[],'snapshots':{}});wait('Ввести адресу');top();navigate('Налаштування');s=wait('Дозволи та фонова робота','Про застосунок');assert 'current-address-card' not in s;flags['emptySettingsRemainGlobal']=True;evidence('settings-no-places',s)
finally:
 result={'api':adb('shell','getprop','ro.build.version.sdk').strip(),'apkSha256':c['meta']['sha256'],'flags':flags,'allPassed':len(flags)==12 and all(flags.values())};(out/'settings-ui-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print('SETTINGS_UI_RESULT',json.dumps(result),flush=True)
