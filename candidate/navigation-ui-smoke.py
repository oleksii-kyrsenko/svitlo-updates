"""Navigation and source-card layout in the signed APK, using external QA state."""
import pathlib,json,copy,re,xml.etree.ElementTree as E
s=pathlib.Path('candidate/settings-ui-smoke.py').read_text().split('\ntry:')[0]
c={'__name__':'navigation_helpers'};exec(compile(s,'navigation_helpers','exec'),c)
adb=c['adb'];xml=c['xml'];tap=c['tap'];wait=c['wait'];top=c['top'];seed=c['seed'];launch=c['launch'];evidence=c['evidence'];navigate=c['navigate'];source_wait=c['source_wait'];out=c['out'];pkg=c['pkg'];bounds=c['c']['bounds'];flags={}
def by_id(tree,name):return next((n for n in tree.iter('node') if n.get('resource-id','').split('/')[-1]==name),None)
def inside(a,b):return len(a)==len(b)==4 and a[0]<=b[0]<b[2]<=a[2] and a[1]<=b[1]<b[3]<=a[3]
try:
 state=json.loads(pathlib.Path('candidate/fixture.json').read_text());first=state['places'][0];first.update(name='QA Home',queueOrigin='manual',queueConfirmed=True)
 other=copy.deepcopy(first);other.update(id='navigation-work',name='QA Work');state.update(places=[first,other],activePlaceId=first['id'],snapshots={})
 seed(state);s=wait('place-select','QA Home','Меню застосунку');assert '⚙' not in s and '▥ Графік' not in s and '＋ Додати адресу' not in s;flags['noWheelOrBottomNavigation']=True;evidence('navigation-home',s)
 tap('Меню застосунку');s=wait('app-menu','Мої адреси','Додати адресу');assert s.index('Налаштування')<s.index('Мої адреси')<s.index('Додати адресу');flags['threeOrderedMenuActions']=True;evidence('navigation-menu',s)
 adb('shell','input','keyevent','4');s=wait('place-select','QA Home');assert 'app-menu"' not in s;flags['menuBackDismisses']=True
 navigate('Мої адреси');s=wait('my-addresses-screen','QA Home','QA Work');assert 'place-select' not in s and 'delete-place' not in s;evidence('navigation-addresses',s)
 tap('Обрати адресу: QA Work');s=wait('place-select','QA Work');assert 'my-addresses-screen' not in s;flags['addressListSelectsSchedule']=True
 persisted=c['state_read']();assert persisted['activePlaceId']==other['id'];launch();wait('place-select','QA Work');flags['selectionSurvivesRestart']=True
 navigate('Мої адреси');wait('my-addresses-screen');adb('shell','input','keyevent','4');wait('place-select','QA Work');flags['androidBackReturnsToSchedule']=True
 s=source_wait('Редагувати адресу','Черга 3.1');tree=E.fromstring(s);source=by_id(tree,'schedule-source');address=by_id(tree,'address-block');assert source is not None and address is not None and inside(bounds(source),bounds(address));flags['addressAndEditInsideSource']=True;evidence('navigation-source-address',s)
 top();navigate('＋ Додати адресу');s=wait('Вибір адреси','Введіть адресу');assert 'delete-place' not in s;tap('Закрити');wait('place-select');flags['menuAddOpensNewAddress']=True
 navigate('Мої адреси');wait('my-addresses-screen');tap('＋ Додати адресу');wait('Вибір адреси');tap('Закрити');wait('my-addresses-screen');flags['listAddReturnsToAddressList']=True
finally:
 result={'api':adb('shell','getprop','ro.build.version.sdk').strip(),'flags':flags,'apkSha256':c['c']['meta']['sha256'],'allPassed':len(flags)==9 and all(flags.values())};(out/'navigation-ui-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print('NAVIGATION_UI_RESULT',json.dumps(result),flush=True)
