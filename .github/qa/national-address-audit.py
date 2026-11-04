"""Audit a pinned signed APK through its visible UI; never seed an address or queue.

Appium only supplies Unicode typing and the accessibility tree. All choices and
save actions use the app's controls. SQLite is read solely to verify what the app
actually persisted, and is never written by this audit.
"""
import argparse, base64, datetime, hashlib, importlib.util, json, os, pathlib, re, sqlite3, subprocess, time, traceback
import urllib.error, urllib.request, urllib.parse, xml.etree.ElementTree as ET

_spec=importlib.util.spec_from_file_location('audit_contract',pathlib.Path(__file__).with_name('audit-contract.py'))
audit_contract=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(audit_contract)

PKG = 'ua.svitlo.app.testing'
EID = 'element-6066-11e4-a52e-4f735466cecf'
REVIEWED_DISPLAY_VARIANTS = pathlib.Path(__file__).with_name('capital-reviewed-display-variants.json')
REVIEWED_DISPLAY_VARIANTS_SHA256 = '5bf4f083c9740e4f552acd39ed668f8a9d01cf2b0c50c437b0d88a7bfc57c8df'
REVIEWED_BASELINE_SHA256 = '369aa30d4e4ec1f502b4d996f53b4555df953682ef4bf0449198d7c6eca97043'
REVIEWED_CASE_IDS = {'UA-73-capital-1','UA-73-capital-2','UA-46-capital-2'}


def stamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def norm(value):
    return re.sub(r'\s+', ' ', value.lower().replace('’', "'").replace('ʼ', "'")).strip()


def queue_lookup_pending(text):
    return any(label in text for label in (
        'Перевіряємо чергу за адресою',
        'Шукаємо чергу за адресою',
        'Чергу ще перевіряємо',
    ))


def street_identity(value):
    value=norm(value).strip(' .,-')
    types=[('вулиця',r'вулиця|вул\.?'),('провулок',r'провулок|пров\.?'),('проспект',r'проспект|просп\.?|пр-т'),('площа',r'площа|пл\.?'),('бульвар',r'бульвар|бульв\.?|бул\.?'),('узвіз',r'узвіз'),('набережна',r'набережна'),('шосе',r'шосе'),('алея',r'алея'),('тупик',r'тупик'),('проїзд',r'проїзд'),('дорога',r'дорога')]
    for canonical,kind in types:
        prefix=re.match(r'^(?:'+kind+r')\s+',value)
        suffix=re.search(r'\s+(?:'+kind+r')$',value)
        if prefix:return canonical,norm(value[prefix.end():]).strip(' .,-')
        if suffix:return canonical,norm(value[:suffix.start()]).strip(' .,-')
    return None,value


def street_key(value):
    kind,name=street_identity(value)
    return (kind or '')+'|'+name


def street_name_key(value):
    text=norm(value)
    reduced=re.sub(r'\b(?:гетьмана|митрополита)\b', ' ', text)
    reduced=re.sub(r'\bгероя\s+україни\b', ' ', reduced)
    words=reduced.split()
    return tuple(sorted(words if len(words)>=2 else text.split()))


def street_matches(label,target):
    target_kind,target_name=street_identity(target)
    current_kind,_=street_identity(label.split(' · ')[0])
    for part in label.split(' · '):
        old=part.startswith('раніше ')
        kind,name=street_identity(re.sub(r'^раніше\s+', '', part))
        if old and kind is None:kind=current_kind
        if kind==target_kind and street_name_key(name)==street_name_key(target_name):return True
    return False


def validate_reviewed_display_metadata(metadata,cases):
    variants=metadata.get('variants')
    if not isinstance(variants,dict) or set(variants)!=REVIEWED_CASE_IDS:
        raise ValueError('Only the three previously reviewed baseline aliases are permitted')
    indexed={case['id']:case for case in cases}
    if len(indexed)!=len(cases) or not REVIEWED_CASE_IDS.issubset(indexed):
        raise ValueError('Reviewed aliases require the unchanged complete baseline case identities')
    short=metadata.get('lvivShortNameEvidence') or {}
    url=urllib.parse.urlsplit(short.get('url',''))
    query=urllib.parse.parse_qs(url.query)
    parts=[value.strip() for value in query.get('q',[''])[0].split(',')]
    lviv=indexed['UA-46-capital-2']
    if (url.scheme!='https' or url.hostname!='nominatim.openstreetmap.org' or url.path!='/search' or
        url.username or url.password or query.get('countrycodes')!=['ua'] or len(parts)!=3 or
        norm(parts[0])!=norm(lviv['city']) or norm(parts[2])!=norm(lviv['exactHouse']) or
        lviv.get('osmType')!='way' or short.get('sameFrozenOsmId')!=lviv.get('osmId')):
        raise ValueError('Reviewed short-name evidence differs from the frozen OSM building or house')
    short_name=parts[1]
    if short_name not in variants['UA-46-capital-2']:
        raise ValueError('Short-name proof does not identify one of the reviewed labels')
    for case_id,names in variants.items():
        case=indexed[case_id];kind,full_name=street_identity(case['exactStreet'])
        if not isinstance(names,list) or not names or len(names)>5 or len(set(names))!=len(names):
            raise ValueError('Invalid reviewed street label list')
        for name in names:
            if not isinstance(name,str) or not name.strip() or len(name)>250 or re.search(r'[,;\d]',name):
                raise ValueError('Reviewed person-name street aliases cannot include a house or another address')
            alias_kind,alias_name=street_identity(name)
            if not kind or alias_kind!=kind:
                raise ValueError('Reviewed street alias changes the frozen street type')
            if case_id=='UA-46-capital-2' and name==short_name:
                continue
            if street_name_key(alias_name)!=street_name_key(full_name):
                raise ValueError('Reviewed street alias changes the complete person name')
    return variants


def attach_reviewed_display_variants(cases,sample_sha256,path=REVIEWED_DISPLAY_VARIANTS):
    raw=pathlib.Path(path).read_bytes();actual=hashlib.sha256(raw).hexdigest()
    if actual!=REVIEWED_DISPLAY_VARIANTS_SHA256:
        raise ValueError('Reviewed display alias artifact differs from its pinned review')
    # A holdout never receives these baseline-only exceptions, even if a case
    # supplies a similarly named field. The geographic fixture itself is untouched.
    aliases=validate_reviewed_display_metadata(json.loads(raw),cases) if sample_sha256==REVIEWED_BASELINE_SHA256 else {}
    result=[]
    for case in cases:
        copy={k:v for k,v in case.items() if k not in ['reviewedDisplayStreetVariants','reviewedDisplayVariantsSha256']}
        copy['reviewedDisplayVariantsSha256']=actual
        if case['id'] in aliases:copy['reviewedDisplayStreetVariants']=list(aliases[case['id']])
        result.append(copy)
    return result,actual,raw


def case_street_variants(case):
    reviewed=case.get('reviewedDisplayStreetVariants',[]) if case.get('reviewedDisplayVariantsSha256')==REVIEWED_DISPLAY_VARIANTS_SHA256 and case.get('id') in REVIEWED_CASE_IDS else []
    return list(dict.fromkeys([case['exactStreet'],*case.get('confirmedStreetVariants',[]),*reviewed]))


def case_street_queries(case):
    queries=[]
    for name in case_street_variants(case):
        core=street_identity(name)[1]
        queries.extend([core,' '.join(street_name_key(core)),max(core.split(),key=len) if core.split() else core])
    return list(dict.fromkeys(query for query in queries if query))


def validate_saved_address(case,result,place):
    selection=place.get('addressSelection') or {}
    street=selection.get('street') or {};house=selection.get('house') or {}
    if not selection.get('city',{}).get('id'):raise RuntimeError('Saved city was not selected through the UI')
    origin=place.get('addressOrigin')
    if origin=='postal':
        if not street.get('id'):raise RuntimeError('Saved postal street has no directory identity')
    elif origin=='structured':
        typed=street.get('manual') is True and result.get('streetEnteredThroughUI') is True and street.get('source')=='user'
        official=street.get('source')=='official-roster' and bool(street.get('id')) and not result.get('streetEnteredThroughUI')
        if not(typed or official):raise RuntimeError('Structured street lacks visible typed action or selected official entry')
    else:raise RuntimeError('Unsupported saved address origin')
    if not(house.get('id') or result.get('houseEnteredThroughUI') or (house.get('source')=='official-roster' and result.get('houseSelectedFromList'))):raise RuntimeError('House was not selected or entered through the UI')
    parts=place.get('addressParts') or {}
    if norm(parts.get('settlement',''))!=norm(case['city']):raise RuntimeError('Saved city differs from frozen target')
    variants=case_street_variants(case)
    if not any(street_matches(parts.get('street',''),variant) for variant in variants):raise RuntimeError('Saved street/type differs from frozen target')
    if norm(parts.get('house',''))!=norm(case['exactHouse']):raise RuntimeError('Saved house/letter/corpus differs from frozen target')


class SearchInputNotCommitted(RuntimeError):
    def __init__(self,label,state):
        self.state=state
        super().__init__('Search input was not committed by the app: '+label+'; '+json.dumps(state,ensure_ascii=False))


class AddressSearchTimeout(RuntimeError):
    """The app accepted the query, but its visible address list stayed pending."""
    def __init__(self,label,xml):
        self.xml=xml
        super().__init__('Address source still loading after accepted search: '+label)


def search_input_state(xml, label, text):
    nodes=list(ET.fromstring(xml).iter())
    inputs=[n for n in nodes if n.get('class')=='android.widget.EditText' and
            n.get('content-desc')=='Пошук: '+label and n.get('displayed')!='false']
    values=[n.get('text','') for n in inputs]
    native_matches=len(inputs)==1 and norm(values[0])==norm(text)
    clear=any(n.get('displayed')!='false' and n.get('enabled')!='false' and
              (n.get('resource-id','').split('/')[-1]=='address-search-input-clear' or
               n.get('content-desc')=='Очистити пошук') for n in nodes)
    loading=any(n.get('displayed')!='false' and
                (n.get('class')=='android.widget.ProgressBar' or
                 n.get('resource-id','').split('/')[-1]=='ui-loader' or
                 n.get('content-desc')=='Завантаження') for n in nodes)
    # Native ACTION_SET_TEXT can update EditText before React consumes its
    # change event. The app-owned Clear button proves the controlled value;
    # loading is not a substitute for that proof (Input does not hide Clear).
    committed=native_matches and (clear if text else not clear)
    return {'nativeMatches':native_matches,'committed':committed,'loading':loading,
            'observedValues':values,'clearVisible':clear}


class Audit:
    def __init__(self, apk, out, contract=None):
        self.contract=contract or audit_contract.contract({})
        audit_contract.verify_apk(apk,self.contract)
        self.out = out
        self.case_dir = out/'startup'
        self.case_dir.mkdir(exist_ok=True,parents=True)
        self.system_recoveries = 0
        self.sid = None
        caps = {'platformName': 'Android', 'appium:automationName': 'UiAutomator2',
                'appium:app': str(apk.resolve()), 'appium:appPackage': PKG,
                'appium:appActivity': '.MainActivity', 'appium:noReset': True,
                'appium:hideKeyboard': True,
                'appium:newCommandTimeout': 600, 'appium:adbExecTimeout': 120000,
                'appium:uiautomator2ServerInstallTimeout': 120000,
                'appium:settings[waitForIdleTimeout]': 100,
                'appium:settings[waitForSelectorTimeout]': 100}
        self.sid = self.request('POST', '/session', {'capabilities': {'alwaysMatch': caps}})['sessionId']
        self.verify_installed_apk()
        self.size = self.call('GET', '/window/rect')
        time.sleep(5)
        try:
            self.wait(lambda x: 'КОЛИ СВІТЛО' in x or 'Ввести адресу' in x, 55)
        except Exception:
            self.screenshot('startup-failed')
            (self.case_dir/'startup.log').write_text(self.adb('logcat','-d'))
            raise

    def verify_installed_apk(self):
        api=int(self.adb('shell','getprop','ro.build.version.sdk').strip())
        if api!=self.contract['androidApi']:raise RuntimeError('Emulator API differs from the requested audit')
        paths=[line.removeprefix('package:').strip() for line in self.adb('shell','pm','path',PKG).splitlines() if line.startswith('package:')]
        if len(paths)!=1 or not paths[0].startswith('/data/app/') or not paths[0].endswith('.apk'):
            raise RuntimeError('Unexpected installed package/split structure')
        digest=self.adb('shell','sha256sum',paths[0]).split()[0]
        if digest!=self.contract['apkSha256']:raise RuntimeError('Installed APK differs from the pinned download')
        self.installed_apk_sha256=digest
        (self.case_dir/'installed-binary.json').write_text(json.dumps({'packageName':PKG,'apkSha256':digest,'androidApi':api,'versionCode':self.contract['versionCode'],'version':self.contract['version']},indent=2)+'\n')

    def request(self, method, path, data=None):
        payload = None if data is None else json.dumps(data, ensure_ascii=False).encode()
        req = urllib.request.Request('http://127.0.0.1:4723' + path, payload,
                                     {'Content-Type': 'application/json'}, method=method)
        try:
            with urllib.request.urlopen(req, timeout=150) as response:
                value = json.load(response)['value']
        except urllib.error.HTTPError as error:
            raise RuntimeError(error.read().decode()[:1600]) from error
        if isinstance(value, dict) and value.get('error'):
            raise RuntimeError(str(value)[:1600])
        return value

    def call(self, method, path, data=None):
        return self.request(method, '/session/' + self.sid + path, data)

    def adb(self, *args, check=True):
        run = subprocess.run(['adb', *args], capture_output=True, text=True, timeout=50)
        if check and run.returncode:
            raise RuntimeError(run.stderr[:1000] or run.stdout[:1000])
        return run.stdout

    def source(self):
        xml = self.call('GET', '/source')
        # Recover only explicitly identified emulator system processes. A
        # Svitlo ANR is retained as a failure and is never dismissed here.
        messages={norm(n.get('text','')) for n in ET.fromstring(xml).iter()}
        if norm('Viewing full screen') in messages and norm('Got it') in messages:
            self.screenshot('android-fullscreen-tip', xml)
            node = next(n for n in ET.fromstring(xml).iter() if norm(n.get('text','')) == norm('Got it'))
            self.click_node(node)
            time.sleep(.5)
            return self.call('GET', '/source')
        known_system_anrs={norm(name) for name in ["Pixel Launcher isn't responding", "System UI isn't responding",
            "com.google.android.googlesdksetup isn't responding"]}
        if messages & known_system_anrs:
            self.system_recoveries += 1
            self.screenshot('emulator-system-anr-'+str(self.system_recoveries),xml)
            if self.system_recoveries>2:
                raise RuntimeError('Emulator system ANR repeated')
            close = next((n for n in ET.fromstring(xml).iter() if norm(n.get('text',''))=='close app'),None)
            if close is None:
                raise RuntimeError('Emulator system ANR has no close action')
            self.click_node(close)
            self.adb('shell','am','start','-W','-n',PKG+'/.MainActivity')
            time.sleep(4)
            return self.call('GET','/source')
        return xml

    def wait(self, predicate, seconds=25):
        until = time.monotonic() + seconds
        while True:
            xml = self.source()
            if predicate(xml):
                return xml
            if time.monotonic() >= until:
                raise RuntimeError('UI wait timed out')
            time.sleep(.65)

    def screenshot(self, name, xml=None):
        xml = xml or self.source()
        (self.case_dir / (name + '.xml')).write_text(xml)
        (self.case_dir / (name + '.png')).write_bytes(base64.b64decode(self.call('GET', '/screenshot')))
        return xml

    def scroll(self, down=True):
        w, h = self.size['width'], self.size['height']
        self.adb('shell', 'input', 'swipe', str(w//2), str(int(h*(.76 if down else .37))),
                 str(w//2), str(int(h*(.37 if down else .76))), '320')
        time.sleep(.3)

    def box(self, node):
        nums = list(map(int, re.findall(r'\d+', node.get('bounds', ''))))
        return nums if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] else None

    def click_node(self, node):
        b = self.box(node)
        if not b:
            raise RuntimeError('Option has no visible bounds')
        if node.get('content-desc'):
            element = self.call('POST', '/element', {'using':'accessibility id','value':node.get('content-desc')})[EID]
            self.call('POST', '/element/'+element+'/click', {})
        else:
            self.adb('shell', 'input', 'tap', str((b[0]+b[2])//2), str((b[1]+b[3])//2))
        time.sleep(.35)

    def choose_option(self, node):
        label = node.get('content-desc')
        for _ in range(3):
            self.click_node(node)
            try:
                self.wait(lambda x:'Закрити список адрес' not in x, 2)
                return
            except RuntimeError:
                # The transition may finish between the bounded wait's final
                # observation and the retry tree. Confirm that current tree
                # before treating a missing option as a selection failure.
                current = self.source()
                if 'Закрити список адрес' not in current:
                    return
                nodes = self.options(current)
                node = next((n for n in nodes if n.get('content-desc')==label), None)
                if node is None:
                    break
        raise RuntimeError('Selected address option did not close its list: '+label)

    def tap(self, label, scroll=False, required=True):
        for _ in range(9 if scroll else 2):
            xml = self.source()
            for node in ET.fromstring(xml).iter():
                if any(norm(label)==norm(value or '') for value in (node.get('content-desc'),node.get('text'),node.get('resource-id'))) or node.get('resource-id', '').endswith('/'+label):
                    if self.box(node) and node.get('enabled') != 'false':
                        self.click_node(node)
                        return True
            if scroll:
                self.scroll()
            else:
                time.sleep(.5)
        if required:
            raise RuntimeError('UI action unavailable: ' + label)
        return False

    def wait_search_commit(self, label, text, seconds=6, loading_seconds=45):
        start=time.monotonic()
        while True:
            xml=self.source();state=search_input_state(xml,label,text)
            if state['committed']:
                return xml
            elapsed=time.monotonic()-start
            # Do not keep replacing already-correct native text while the app
            # is busy opening its first city directory. Retrying would race
            # the same pending React event; keep one bounded wait instead.
            limit=loading_seconds if state['nativeMatches'] and state['loading'] else seconds
            if elapsed>=limit:
                raise SearchInputNotCommitted(label,state)
            time.sleep(.65)

    def type_search(self, label, text):
        self.current_query = text
        self.current_field = label
        self.phase = 'type-search-'+label
        for attempt in range(3):
            self.source()  # Dismiss an identified Android fullscreen onboarding tip.
            element = self.call('POST','/element',{'using':'accessibility id','value':'Пошук: '+label})[EID]
            self.call('POST','/element/'+element+'/click',{})
            if attempt<2:
                # One native EditText replacement avoids racing a Clear event
                # with a temporary Unicode IME switch. It still uses the real
                # visible input and must update React's Clear-search control.
                self.call('POST','/execute/sync',{'script':'mobile: replaceElementValue',
                    'args':[{'elementId':element,'text':text}]})
            else:
                self.call('POST','/element/'+element+'/clear',{})
                time.sleep(.6)
                if text:
                    # Unicode IME can intermittently type its encoded transport
                    # payload. Paste through Android's native clipboard instead;
                    # the same visible EditText/content assertion still applies.
                    self.call('POST','/execute/sync',{'script':'mobile: setClipboard','args':[{
                        'content':base64.b64encode(text.encode('utf-8')).decode('ascii'),
                        'contentType':'plaintext'}]})
                    self.adb('shell','input','keyevent','279')
            try:
                self.wait_search_commit(label,text)
                time.sleep(.65)
                return
            except RuntimeError as error:
                self.screenshot('search-input-retry-'+str(len(self.input_retries)))
                self.input_retries.append({'field':label,'attempt':attempt+1})
                if isinstance(error,SearchInputNotCommitted) and error.state['nativeMatches'] and error.state['loading']:
                    # Replacing the same pending value again cannot establish
                    # React commitment. Preserve this bounded busy-state failure.
                    raise
        raise RuntimeError('Native search input did not accept text: '+label)

    def options(self, xml):
        exclude = ('Пошук:', 'Закрити', 'Очистити', 'Застосувати', 'Повторити')
        return [n for n in ET.fromstring(xml).iter() if n.get('content-desc')
                and n.get('clickable') == 'true' and self.box(n)
                and not n.get('content-desc').startswith(exclude)
                and n.get('class') != 'android.widget.EditText']

    def wait_options(self, seconds=45):
        until = time.monotonic()+seconds
        while True:
            xml = self.source()
            if 'Закрити список адрес' not in xml or 'Пошук:' not in xml:
                raise RuntimeError('Address list closed before an option was selected')
            state=search_input_state(xml,getattr(self,'current_field',''),getattr(self,'current_query',''))
            if not state['committed']:
                raise RuntimeError('Address search input changed after typing: '+json.dumps(state,ensure_ascii=False))
            options = self.options(xml)
            if options:
                query=getattr(self,'current_query','')
                if getattr(self,'current_field',None)=='Вулиця':
                    tokens=re.findall(r'[\w\d]+',street_key(query))
                    matching=[n for n in options if all(token in street_key(n.get('content-desc')) for token in tokens)]
                else:
                    tokens = re.findall(r'[\w\d]+',norm(query))
                    matching = [n for n in options if all(token in norm(n.get('content-desc')) for token in tokens)]
                if matching:
                    return matching, xml
            loading=state['loading']
            if not loading and ('Нічого не знайдено' in xml or 'не відповів' in xml or 'недоступн' in xml or 'Номера немає' in xml):
                return [], xml
            if time.monotonic() > until:
                if loading:raise AddressSearchTimeout(getattr(self,'current_field',''),xml)
                return [], xml
            time.sleep(.65)

    def field(self, label, query):
        self.tap('Обрати: '+label, scroll=True)
        self.wait(lambda x: 'Пошук: '+label in x)
        self.type_search(label, query)
        return self.wait_options()

    def read_state(self):
        # Pulling a live SQLite directory can catch a hot journal. Keep each
        # original capture, including its sidecars, and retry a fresh pull only
        # for SQLite's explicit read-only recovery error. Never ignore a journal
        # or modify the database on the device to make an audit pass.
        root = self.case_dir/'database'
        for attempt in range(3):
            index=getattr(self,'database_capture_count',0)+1
            while (root/('capture-'+str(index).zfill(3))).exists():index+=1
            self.database_capture_count=index
            directory=root/('capture-'+str(index).zfill(3));directory.mkdir(parents=True)
            self.adb('pull', f'/data/data/{PKG}/databases', str(directory), check=False)
            capture={'capturedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),
                     'readOnly':True,'files':[{'path':str(p.relative_to(directory)),'size':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(directory.rglob('*')) if p.is_file()]}
            proof=directory/'capture.json';proof.write_text(json.dumps(capture,ensure_ascii=False,indent=2)+'\n')
            db = next(directory.rglob('RKStorage'), None)
            if not db:
                return {}
            try:
                with sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True) as connection:
                    self.coverage_snapshot=None;self.city_coverage_snapshot=None
                    for schema,key in [(1,'@svitlo/dynamic-coverage-v1'),(2,'@svitlo/dynamic-coverage-v2')]:
                        coverage=connection.execute('SELECT value FROM catalystLocalStorage WHERE key=?',(key,)).fetchone()
                        if not coverage:continue
                        try:
                            envelope=json.loads(coverage[0]);manifest=json.loads(base64.b64decode(envelope['payload']));snapshot={k:manifest.get(k) for k in ['schemaVersion','revision','generatedAt','expiresAt','enabled']};snapshot['envelopeSha256']=hashlib.sha256(coverage[0].encode()).hexdigest()
                        except (ValueError,KeyError):snapshot={'unparsed':True}
                        if schema==1:self.coverage_snapshot=snapshot
                        else:self.city_coverage_snapshot=snapshot
                    row = connection.execute('SELECT value FROM catalystLocalStorage WHERE key=?', ('svitlo.state.v1',)).fetchone()
            except sqlite3.OperationalError as error:
                if str(error)!='attempt to write a readonly database':raise
                capture.update(captureError='sqlite-readonly-hot-journal-recovery',retry=attempt<2)
                proof.write_text(json.dumps(capture,ensure_ascii=False,indent=2)+'\n')
                if attempt==2:raise
                time.sleep(.25)
                continue
            capture['readCompleted']=True;proof.write_text(json.dumps(capture,ensure_ascii=False,indent=2)+'\n')
            return json.loads(row[0]) if row else {}

    def open_new_editor(self):
        self.phase = 'return-to-main-screen'
        for _ in range(12):
            xml = self.source()
            if 'Незбережені зміни буде втрачено' in xml:
                self.tap('Відкинути зміни')
            elif 'Закрити список адрес' in xml and self.tap('Закрити список адрес',required=False):
                pass
            elif 'Налаштування адреси' in xml:
                self.tap('Закрити')
            elif 'Закрити вибір місця' in xml:
                self.tap('Закрити вибір місця')
            else:
                if self.tap('Ввести адресу',required=False) or self.tap('Додати адресу',required=False):
                    self.wait(lambda x:'Обрати: Область' in x,15)
                    return
                # An asynchronous menu transition can complete while the
                # optional add-address actions above are being located. Never
                # act on the old home-screen tree after those round trips.
                current = self.source()
                if 'app-menu-button' in current:
                    self.tap('app-menu-button',required=False)
            time.sleep(1)
        raise RuntimeError('Could not return from the previous editor to a new empty place')

    def run_case(self, case):
        self.case_dir = self.out/case['id']
        self.case_dir.mkdir(exist_ok=True, parents=True)
        self.input_retries = []
        self.phase = 'open-place-editor'
        start = time.monotonic()
        result = {**case, 'startedAt': stamp(), 'method': 'signed-apk-visible-ui', 'stage': 'open', 'uiIssues': [],
                  'auditRunId':os.environ.get('GITHUB_RUN_ID'), 'auditCommit':os.environ.get('GITHUB_SHA'),
                  'reviewedDisplayVariantsSha256':case.get('reviewedDisplayVariantsSha256'),
                  'apkVersion':self.contract['version'], 'apkCode':self.contract['versionCode'], 'apkSha256':self.installed_apk_sha256, 'androidApi':self.contract['androidApi'], 'sampleSha256':self.contract['sampleSha256'], 'queueEnteredManually':False, 'addressStorageSeeded':False}
        try:
            self.open_new_editor()
            self.phase = 'select-region'
            options, xml = self.field('Область', case['regionQuery'])
            expected = case.get('regionLabel') or ('Київська область' if case['regionId']=='UA-30' else case['regionQuery']+' область')
            match = next((n for n in options if norm(n.get('content-desc')) == norm(expected)), None)
            if match is None:
                raise RuntimeError('Requested region is absent from app list')
            self.choose_option(match)
            result['stage'] = 'city'
            options, xml = self.field('Населений пункт', case['city'])
            result['cityOptions'] = [n.get('content-desc') for n in options]
            def city_name(label):
                value = label.split(' · ')[0]
                value = re.sub(r'^(?:м\.?|с\.?|с-ще\.?|смт\.?|селище|село|місто)\s+', '', value)
                return norm(re.sub(r'\s*\([^)]*\)', '', value))
            matches = [n for n in options if city_name(n.get('content-desc')) == norm(case['city'])]
            if case.get('exactCityLabel'):
                matches=[n for n in matches if norm(n.get('content-desc'))==norm(case['exactCityLabel'])]
            if len(matches)>1 and case['role'] in ['обласний центр','районний центр','місто окремо']:
                cities=[n for n in matches if re.match(r'^м\.?\s+',n.get('content-desc'))]
                if cities:
                    matches=cities
            if len(matches) > 1 and case.get('cityHint'):
                narrowed = [n for n in matches if norm(case['cityHint']) in norm(n.get('content-desc'))]
                if narrowed:
                    matches = narrowed
            if len(matches)>1 and case.get('allowAnyCommunity'):
                result['selectionNote']='Selected one explicitly listed community; see full city label and KATOTTG.'
                matches=matches[:1]
            if len(matches) != 1:
                result.update(outcome='city_unavailable' if not matches else 'city_ambiguous', visibleText=self.texts(xml))
                return result
            result['selectedCityLabel'] = matches[0].get('content-desc')
            self.screenshot('city-selected-from-list', xml)
            self.choose_option(matches[0])
            result['stage'] = 'street'
            queries=case_street_queries(case) if case.get('exactStreet') else [case.get('preferredStreet','')]
            selected = None
            street_open = False
            tried_streets = set()
            numeric = []
            result['houseDirectoryAttempts'] = []
            for query in queries:
                if not street_open:
                    options, xml = self.field('Вулиця', query)
                    street_open = True
                else:
                    self.type_search('Вулиця', query)
                    options, xml = self.wait_options()
                result['streetOptions']=[n.get('content-desc') for n in options]
                selected = next((n for n in options if n.get('content-desc') not in tried_streets and (not case.get('exactStreet') or any(street_matches(n.get('content-desc'),v) for v in case_street_variants(case)))), None)
                if selected is None:
                    continue
                result['selectedStreetLabel'] = selected.get('content-desc')
                tried_streets.add(result['selectedStreetLabel'])
                self.choose_option(selected)
                street_open = False
                result['stage'] = 'house'
                options, xml = self.field('Будинок', case.get('preferredHouse', ''))
                numeric = [n for n in options if re.match(r'^\d', n.get('content-desc'))]
                if not numeric and case.get('preferredHouse') and not case.get('exactHouse'):
                    self.type_search('Будинок', '')
                    options, xml = self.wait_options()
                    numeric = [n for n in options if re.match(r'^\d', n.get('content-desc'))]
                result['houseDirectoryAttempts'].append({'street':result['selectedStreetLabel'],
                    'visibleHouses':[n.get('content-desc') for n in numeric], 'visibleText':self.texts(xml)})
                if numeric or case.get('exactHouse'):
                    break
                self.screenshot('empty-house-list-'+str(len(tried_streets)), xml)
                if not case.get('exactHouse'):self.tap('Закрити список адрес')
            if not tried_streets and case.get('exactStreet'):
                # A missing postal street is entered only through the app's
                # explicit typed-street action, including its exact street type.
                if not street_open:
                    options,xml=self.field('Вулиця',case['exactStreet'])
                    street_open=True
                else:
                    self.type_search('Вулиця',case['exactStreet'])
                    options,xml=self.wait_options()
                self.screenshot('typed-street-before-apply',xml)
                if self.tap('Застосувати введену вулицю',required=False):
                    self.wait(lambda x:'Закрити список адрес' not in x,5)
                    result['selectedStreetLabel']=case['exactStreet']
                    result['streetEnteredThroughUI']=True
                    tried_streets.add(case['exactStreet'])
                    street_open=False
                    self.screenshot('typed-street-applied')
                    result['stage']='house'
                    options,xml=self.field('Будинок',case['exactHouse'])
                    numeric=[n for n in options if re.match(r'^\d',n.get('content-desc'))]
            if case.get('exactHouse'):
                numeric=[n for n in numeric if norm(n.get('content-desc'))==norm(case['exactHouse'])]
            if not numeric and tried_streets and case.get('exactHouse') and 'Пошук: Будинок' in xml:
                self.screenshot('typed-house-before-apply',xml)
                self.tap('Застосувати номер будинку')
                result['selectedHouse']=case['exactHouse']
                result['houseEnteredThroughUI']=True
            elif not numeric:
                result.update(outcome='house_unavailable' if tried_streets else 'street_unavailable', visibleText=self.texts(xml))
                return result
            houses = [case.get('preferredHouse', ''), '10', '12', '22', '8', '4', '2', '1']
            if numeric:
                selected = next((n for h in houses for n in numeric if norm(n.get('content-desc')) == norm(h)), numeric[0])
                result['selectedHouse'] = selected.get('content-desc')
                self.screenshot('house-selected-from-list', xml)
                self.choose_option(selected)
                result['houseSelectedFromList']=True
            lookup_start = time.monotonic()
            result['addressSelectedThroughUI'] = True
            result['addressFromUI'] = ', '.join([re.sub(r'^(?:м\.?|с\.?|с-ще\.?|смт\.?|селище|село|місто)\s+', '', result['selectedCityLabel'].split(' · ')[0]), result['selectedStreetLabel'].split(' · ')[0], result['selectedHouse']])
            result['stage'] = 'queue'
            # Bring status below the address fields into view. No manual queue is entered.
            self.scroll()
            deadline = time.monotonic()+200
            final_xml = self.source()
            while time.monotonic() < deadline:
                final_xml = self.source()
                texts = self.texts(final_xml)
                joined = ' '.join(texts)
                pending = queue_lookup_pending(joined)
                ready = re.search(r'(?:Черга|Ймовірна черга)\s+([\d.\-]+)\s*·\s*(знайдено автоматично|за офіційним переліком|публічне джерело)', joined)
                if ready:
                    result.update(outcome='queue_found', visibleQueue=ready.group(1))
                    break
                if 'Оберіть оператора в додаткових налаштуваннях' in joined:
                    result['outcome'] = 'operator_missing'
                    break
                if not pending and time.monotonic()-lookup_start > 12:
                    result['outcome'] = 'no_confirmed_queue'
                    break
                time.sleep(1.5)
            else:
                result['outcome'] = 'queue_timeout'
            result['lookupSeconds'] = round(time.monotonic()-lookup_start, 1)
            result['visibleText'] = self.texts(final_xml)
            self.screenshot('queue-result', final_xml)
            # Save using the app control; inspect only the state the APK writes.
            result['stage'] = 'save'
            if self.tap('save-place', required=False):
                self.wait(lambda x: 'Налаштування адреси' not in x, 15)
                time.sleep(3)
                state = self.read_state()
                place = next((p for p in state.get('places', []) if p.get('id') == state.get('activePlaceId')), None)
                result['dynamicCoverageFromApp']=self.coverage_snapshot
                result['cityDynamicCoverageFromApp']=self.city_coverage_snapshot
                result['persistedPlace'] = place
                result['saved'] = bool(place)
                if place:
                    if place.get('queueOrigin') == 'manual':
                        raise RuntimeError('A manually assigned queue cannot count as an audit result')
                    validate_saved_address(case,result,place)
                    result['actualAddress'] = place.get('address')
                    result['snapshot'] = state.get('snapshots', {}).get(place['id'])
                    result['queueOrigin']=place.get('queueOrigin')
                    result['queueCheckStatus']=place.get('queueCheckStatus')
                    result['publicCandidates']=place.get('queuePublicCandidates',[])
                    result['queueTransport']=place.get('queueTransport')
                    if place.get('queueConfirmed') and place.get('queue'):
                        if result.get('visibleQueue')!=place.get('queue'):raise RuntimeError('Visible queue differs from app-written queue')
                        result['outcome']='queue_found_public' if place.get('queueOrigin')=='public' else 'queue_found_official'
                    elif place.get('queuePublicCandidates'):
                        result['outcome']='public_proposal_requires_confirmation'
                    else:result['outcome']=place.get('queueCheckStatus') or result['outcome']
                self.screenshot('saved-in-app')
            else:
                result['saved'] = False
                result['uiIssues'].append('Selected address cannot be saved; see footer and operator selection.')
            result['stage'] = 'complete'
        except AddressSearchTimeout as error:
            result.update(outcome='address_source_timeout',addressSearchError=str(error),
                          addressSearchField=getattr(self,'current_field',None),
                          addressSearchQuery=getattr(self,'current_query',None),visibleText=self.texts(error.xml))
            (self.case_dir/'address-source-timeout.xml').write_text(error.xml)
        except Exception as error:
            result.update(outcome='harness_error', automationError=str(error)[:1800],
                automationPhase=self.phase, automationTraceback=traceback.format_exc())
        finally:
            result['finishedAt'] = stamp()
            result['totalSeconds'] = round(time.monotonic()-start, 1)
            result['automationInputRetries'] = self.input_retries
            try:
                self.screenshot('last-screen')
                log = self.adb('logcat', '-d')
                errors = [line[:2000] for line in log.splitlines() if any(token in line for token in ['FATAL EXCEPTION', 'ReactNativeJS: Error', 'JavascriptException', 'ANR in'])]
                (self.case_dir/'runtime-errors.txt').write_text('\n'.join(errors[-30:]))
            except Exception:
                pass
            (self.case_dir/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
        return result

    @staticmethod
    def texts(xml):
        return list(dict.fromkeys(n.get('text') for n in ET.fromstring(xml).iter() if n.get('text')))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apk', type=pathlib.Path, required=True)
    parser.add_argument('--region', required=True)
    parser.add_argument('--limit', type=int, default=5)
    parser.add_argument('--case-ids', default='')
    parser.add_argument('--contract',type=pathlib.Path)
    parser.add_argument('--sample',type=pathlib.Path)
    parser.add_argument('--out', type=pathlib.Path, default=pathlib.Path('national-audit'))
    args = parser.parse_args()
    args.out.mkdir(exist_ok=True, parents=True)
    binary=audit_contract.contract(json.loads(args.contract.read_text()) if args.contract else {})
    if args.sample and str(args.sample)!=binary['sample']:raise ValueError('Sample override differs from pinned contract')
    data=json.loads(audit_contract.sample_path('.',binary['sample']).read_text())
    data['cases'],alias_sha256,alias_raw=attach_reviewed_display_variants(data['cases'],binary['sampleSha256'])
    (args.out/'reviewed-display-variants.json').write_bytes(alias_raw)
    binary['reviewedDisplayVariantsSha256']=alias_sha256
    if not 1<=args.limit<=20:raise ValueError('Audit limit must be1..20')
    selected = set(filter(None,args.case_ids.split(',')))
    cases = [c for c in data['cases'] if c['regionId'] == args.region and (not selected or c['id'] in selected)][:args.limit]
    assert cases, 'No audit cases selected'
    for attempt in range(4):
        subprocess.run(['adb','root'],capture_output=True,timeout=40)
        subprocess.run(['adb','wait-for-device'],check=True,timeout=60)
        identity=subprocess.run(['adb','shell','id'],capture_output=True,text=True,timeout=30)
        if identity.returncode==0 and 'uid=0' in identity.stdout:
            break
        time.sleep(2)
    else:
        raise RuntimeError('Test emulator did not expose its expected root access')
    audit = Audit(args.apk, args.out,binary)
    results = []
    try:
        for case in cases:
            print('AUDIT_CASE_START', case['id'], case['city'], stamp(), flush=True)
            result = audit.run_case(case)
            results.append(result)
            (args.out/'results.json').write_text(json.dumps({'schemaVersion':1,'apkVersion':binary['version'],'apkCode':binary['versionCode'],'apkSha256':binary['apkSha256'],'androidApi':binary['androidApi'],'sampleSha256':binary['sampleSha256'],'reviewedDisplayVariantsSha256':alias_sha256,'noAddressStorageSeeding':True,'noManualQueueInputs':True,
                'region':args.region,'cases':results}, ensure_ascii=False, indent=2)+'\n')
            print('AUDIT_CASE_RESULT', json.dumps({k:result.get(k) for k in ['id','city','outcome','actualAddress','visibleQueue','lookupSeconds','totalSeconds','automationError']}, ensure_ascii=False), flush=True)
    finally:
        audit.call('DELETE', '')
    if any(r.get('outcome') == 'harness_error' for r in results):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
