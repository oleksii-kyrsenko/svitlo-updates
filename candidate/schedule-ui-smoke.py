"""Native layout and refresh feedback with app-written-style cached test state."""
import pathlib,json,sqlite3,re,time,datetime,zoneinfo,xml.etree.ElementTree as E
source=pathlib.Path('candidate/apk-smoke.py').read_text().split('flags={}')[0]
ctx={'__name__':'schedule_ui_helpers'};exec(compile(source,'native-schedule-ui-helpers','exec'),ctx)
adb=ctx['adb'];out=ctx['out'];pkg=ctx['pkg'];launch=ctx['launch'];wait=ctx['wait_for'];evidence=ctx['evidence'];tap=ctx['tap'];xml=ctx['xml'];bounds=ctx['bounds'];scroll=ctx['scroll_down']
flags={}
def node(tree,id):return next((n for n in tree.iter('node') if n.get('resource-id','').split('/')[-1]==id),None)
def inside(outer,inner):return len(outer)==len(inner)==4 and inner[2]>inner[0] and inner[3]>inner[1] and outer[0]<=inner[0] and outer[1]<=inner[1] and inner[2]<=outer[2] and inner[3]<=outer[3]
# Android exposes these React Native text nodes as accessibility siblings.
# Assert actual visual containment instead of assuming an accessibility parent.
try:
 adb('root',check=False);adb('wait-for-device');adb('shell','am','force-stop',pkg);adb('shell','pm','clear',pkg)
 stamp=int(adb('shell','date','+%s').strip());now=datetime.datetime.fromtimestamp(stamp,datetime.timezone.utc);today=now.astimezone(zoneinfo.ZoneInfo('Europe/Kyiv')).date()
 state=json.loads(pathlib.Path('candidate/fixture.json').read_text());place=state['places'][0];place.update(queueOrigin='manual',queueConfirmed=True,queueCheckedAt=stamp*1000);state.update(activePlaceId=place['id'],notificationsEnabled=False,gpsAsked=True,endpoint='')
 state['snapshots']={place['id']:{key:{'operatorId':place['operatorId'],'queue':place['queue'],'status':'ready','date':(today+datetime.timedelta(days=offset)).isoformat(),'validUntil':(stamp+86400)*1000,'checkedAt':now.isoformat(),'intervals':[]} for key,offset in [('today',0),('tomorrow',1)]}}
 fixture=out/'schedule-ui-RKStorage';fixture.unlink(missing_ok=True)
 with sqlite3.connect(fixture) as db:
  db.execute('CREATE TABLE catalystLocalStorage(key TEXT PRIMARY KEY,value TEXT NOT NULL)');db.execute('PRAGMA user_version=1');db.execute('INSERT INTO catalystLocalStorage VALUES (?,?)',('svitlo.state.v1',json.dumps(state,ensure_ascii=False)))
 remote=f'/data/data/{pkg}/databases/RKStorage';adb('shell','mkdir','-p',f'/data/data/{pkg}/databases');adb('push',str(fixture),remote)
 uid=adb('shell','stat','-c','%u',f'/data/data/{pkg}').strip();assert uid.isdigit();adb('shell','chown','-R',f'{uid}:{uid}',f'/data/data/{pkg}/databases');adb('shell','restorecon','-R',f'/data/data/{pkg}/databases')
 launch();s=wait('schedule-graph','schedule-updated-at');tree=E.fromstring(s);graph=node(tree,'schedule-graph');updated=node(tree,'schedule-updated-at')
 assert updated is not None and updated.get('text','').startswith('Останнє оновлення:') and inside(bounds(graph),bounds(updated));flags['updateTimeInsideDailyChart']=True
 title=next(n for n in tree.iter('node') if n.get('text')=='Графік на добу' and inside(bounds(graph),bounds(n)));assert bounds(updated)[1]>=bounds(title)[3];flags['updateTimeBelowTitle']=True;evidence('schedule-update-time',s)
 for _ in range(8):
  tree=E.fromstring(xml());src=node(tree,'schedule-source')
  if src is not None and any(n.get('text')=='Оновити графік' and inside(bounds(src),bounds(n)) for n in tree.iter('node')):break
  scroll(tree)
 assert src is not None and not any('Останнє оновлення:' in n.get('text','') and inside(bounds(src),bounds(n)) for n in tree.iter('node'));flags['sourceCardHasNoUpdateTime']=True
 tap('Оновити графік',scroll=True);time.sleep(.5);s=xml();assert not any(n.get('class')=='android.widget.ProgressBar' for n in E.fromstring(s).iter('node'));flags['existingContentRefreshHasNoSpinner']=True;evidence('schedule-source-after-refresh',s)
finally:
 result={'api':adb('shell','getprop','ro.build.version.sdk').strip(),'flags':flags,'apkSha256':ctx['meta']['sha256'],'allPassed':len(flags)==4 and all(flags.values())};(out/'schedule-ui-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print('SCHEDULE_UI_RESULT',json.dumps(result),flush=True)
