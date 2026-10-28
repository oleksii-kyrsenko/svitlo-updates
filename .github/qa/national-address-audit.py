"""Audit the released APK through its visible UI; never seed an address or queue.

Appium only supplies Unicode typing and the accessibility tree. All choices and
save actions use the app's controls. SQLite is read solely to verify what the app
actually persisted, and is never written by this audit.
"""
import argparse, base64, datetime, json, os, pathlib, re, sqlite3, subprocess, time, traceback
import urllib.error, urllib.request, xml.etree.ElementTree as ET

PKG = 'ua.svitlo.app.testing'
EID = 'element-6066-11e4-a52e-4f735466cecf'


def stamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def norm(value):
    return re.sub(r'\s+', ' ', value.lower().replace('’', "'").replace('ʼ', "'")).strip()


class Audit:
    def __init__(self, apk, out):
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
        self.size = self.call('GET', '/window/rect')
        time.sleep(5)
        try:
            self.wait(lambda x: 'СВІТЛО' in x or 'Ввести адресу' in x, 55)
        except Exception:
            self.screenshot('startup-failed')
            (self.case_dir/'startup.log').write_text(self.adb('logcat','-d'))
            raise

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
                nodes = self.options(self.source())
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

    def type_search(self, label, text):
        self.current_query = text
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
                self.wait(lambda xml:(not text and 'Очистити пошук' not in xml) or
                    (bool(text) and 'Очистити пошук' in xml and any(
                        n.get('content-desc')=='Пошук: '+label and n.get('text')==text
                        for n in ET.fromstring(xml).iter())), 6)
                time.sleep(.65)
                return
            except RuntimeError:
                self.screenshot('search-input-retry-'+str(len(self.input_retries)))
                self.input_retries.append({'field':label,'attempt':attempt+1})
        raise RuntimeError('Native search input did not accept text: '+label)

    def options(self, xml):
        exclude = ('Пошук:', 'Закрити', 'Очистити', 'Застосувати', 'Повторити')
        return [n for n in ET.fromstring(xml).iter() if n.get('content-desc')
                and n.get('clickable') == 'true' and self.box(n)
                and not n.get('content-desc').startswith(exclude)
                and n.get('class') != 'android.widget.EditText']

    def wait_options(self, seconds=26):
        until = time.monotonic()+seconds
        while True:
            xml = self.source()
            if 'Закрити список адрес' not in xml or 'Пошук:' not in xml:
                raise RuntimeError('Address list closed before an option was selected')
            options = self.options(xml)
            if options:
                tokens = re.findall(r'[\w\d]+',norm(getattr(self,'current_query','')))
                matching = [n for n in options if all(token in norm(n.get('content-desc')) for token in tokens)]
                if matching:
                    return matching, xml
            loading = any(n.get('class') == 'android.widget.ProgressBar' for n in ET.fromstring(xml).iter())
            if not loading and ('Нічого не знайдено' in xml or 'не відповів' in xml or 'недоступн' in xml or 'Номера немає' in xml):
                return [], xml
            if time.monotonic() > until:
                return [], xml
            time.sleep(.65)

    def field(self, label, query):
        self.tap('Обрати: '+label, scroll=True)
        self.wait(lambda x: 'Пошук: '+label in x)
        self.type_search(label, query)
        return self.wait_options()

    def read_state(self):
        directory = self.case_dir/'database'
        directory.mkdir(exist_ok=True)
        self.adb('pull', f'/data/data/{PKG}/databases', str(directory), check=False)
        db = next(directory.rglob('RKStorage'), None)
        if not db:
            return {}
        with sqlite3.connect(db) as connection:
            row = connection.execute('SELECT value FROM catalystLocalStorage WHERE key=?', ('svitlo.state.v1',)).fetchone()
        return json.loads(row[0]) if row else {}

    def open_new_editor(self):
        self.phase = 'return-to-main-screen'
        for _ in range(12):
            xml = self.source()
            if 'Незбережені зміни буде втрачено' in xml:
                self.tap('Відкинути зміни')
            elif 'Закрити список адрес' in xml:
                self.tap('Закрити список адрес')
            elif 'Вибір місця' in xml:
                self.tap('Закрити')
            elif 'Закрити вибір місця' in xml:
                self.tap('Закрити вибір місця')
            else:
                if self.tap('Ввести адресу',required=False) or self.tap('＋ Додати місце',required=False):
                    self.wait(lambda x:'Обрати: Область' in x,15)
                    return
            time.sleep(1)
        raise RuntimeError('Could not return from the previous editor to a new empty place')

    def run_case(self, case):
        self.case_dir = self.out/case['id']
        self.case_dir.mkdir(exist_ok=True, parents=True)
        self.input_retries = []
        self.phase = 'open-place-editor'
        start = time.monotonic()
        result = {**case, 'startedAt': stamp(), 'method': 'released-apk-visible-ui', 'stage': 'open', 'uiIssues': [],
                  'auditRunId':os.environ.get('GITHUB_RUN_ID'), 'auditCommit':os.environ.get('GITHUB_SHA'),
                  'apkVersion':'0.1.30', 'apkCode':62, 'androidApi':35}
        try:
            self.open_new_editor()
            self.phase = 'select-region'
            options, xml = self.field('Область', case['regionQuery'])
            expected = case['regionQuery']+' область'
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
            queries = list(dict.fromkeys([case.get('preferredStreet', 'Шевченка'), 'Миру', 'Садова', '']))
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
                selected = next((n for n in options if n.get('content-desc') not in tried_streets), None)
                if selected is None:
                    continue
                result['selectedStreetLabel'] = selected.get('content-desc')
                tried_streets.add(result['selectedStreetLabel'])
                self.choose_option(selected)
                street_open = False
                result['stage'] = 'house'
                options, xml = self.field('Будинок', case.get('preferredHouse', ''))
                numeric = [n for n in options if re.match(r'^\d', n.get('content-desc'))]
                if not numeric and case.get('preferredHouse'):
                    self.type_search('Будинок', '')
                    options, xml = self.wait_options()
                    numeric = [n for n in options if re.match(r'^\d', n.get('content-desc'))]
                result['houseDirectoryAttempts'].append({'street':result['selectedStreetLabel'],
                    'visibleHouses':[n.get('content-desc') for n in numeric], 'visibleText':self.texts(xml)})
                if numeric:
                    break
                self.screenshot('empty-house-list-'+str(len(tried_streets)), xml)
                self.tap('Закрити список адрес')
            if not numeric:
                result.update(outcome='house_unavailable' if tried_streets else 'street_unavailable', visibleText=self.texts(xml))
                return result
            houses = [case.get('preferredHouse', ''), '10', '12', '22', '8', '4', '2', '1']
            selected = next((n for h in houses for n in numeric if norm(n.get('content-desc')) == norm(h)), numeric[0])
            result['selectedHouse'] = selected.get('content-desc')
            self.screenshot('house-selected-from-list', xml)
            self.choose_option(selected)
            lookup_start = time.monotonic()
            result['addressSelectedThroughUI'] = True
            result['addressFromUI'] = ', '.join([re.sub(r'^(?:м\.?|с\.?|с-ще\.?|смт\.?|селище|село|місто)\s+', '', result['selectedCityLabel'].split(' · ')[0]), result['selectedStreetLabel'].split(' · ')[0], result['selectedHouse']])
            result['stage'] = 'queue'
            # Bring status below the address fields into view. No manual queue is entered.
            for _ in range(4):
                self.scroll()
            deadline = time.monotonic()+200
            final_xml = self.source()
            while time.monotonic() < deadline:
                final_xml = self.source()
                texts = self.texts(final_xml)
                joined = ' '.join(texts)
                pending = 'Перевіряємо чергу за адресою' in joined
                ready = re.search(r'Черга\s+([\d.\-]+)\s*·\s*(знайдено автоматично|за офіційним переліком)', joined)
                if ready:
                    result.update(outcome='queue_found', visibleQueue=ready.group(1))
                    break
                if 'Оберіть оператора в додаткових налаштуваннях' in joined:
                    result['outcome'] = 'operator_missing'
                    break
                if not pending and time.monotonic()-lookup_start > 6:
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
                self.wait(lambda x: 'Вибір місця' not in x, 15)
                time.sleep(3)
                state = self.read_state()
                place = next((p for p in state.get('places', []) if p.get('id') == state.get('activePlaceId')), None)
                result['persistedPlace'] = place
                result['saved'] = bool(place)
                if place:
                    if place.get('queueOrigin') == 'manual':
                        raise RuntimeError('A manually assigned queue cannot count as an audit result')
                    selection = place.get('addressSelection') or {}
                    if place.get('addressOrigin') != 'postal' or not all(selection.get(k,{}).get('id') for k in ['city','street','house']):
                        raise RuntimeError('Saved address was not fully selected from the postal UI')
                    result['actualAddress'] = place.get('address')
                    result['snapshot'] = state.get('snapshots', {}).get(place['id'])
                self.screenshot('saved-in-app')
            else:
                result['saved'] = False
                result['uiIssues'].append('Selected address cannot be saved; see footer and operator selection.')
            result['stage'] = 'complete'
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
    parser.add_argument('--limit', type=int, default=4)
    parser.add_argument('--case-ids', default='')
    parser.add_argument('--out', type=pathlib.Path, default=pathlib.Path('national-audit'))
    args = parser.parse_args()
    args.out.mkdir(exist_ok=True, parents=True)
    data = json.loads(pathlib.Path('.github/qa/national-address-cases.json').read_text())
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
    audit = Audit(args.apk, args.out)
    results = []
    try:
        for case in cases:
            print('AUDIT_CASE_START', case['id'], case['city'], stamp(), flush=True)
            result = audit.run_case(case)
            results.append(result)
            (args.out/'results.json').write_text(json.dumps({'schemaVersion':1, 'apkVersion':'0.1.30', 'apkCode':62,
                'region':args.region, 'cases':results}, ensure_ascii=False, indent=2)+'\n')
            print('AUDIT_CASE_RESULT', json.dumps({k:result.get(k) for k in ['id','city','outcome','actualAddress','visibleQueue','lookupSeconds','totalSeconds','automationError']}, ensure_ascii=False), flush=True)
    finally:
        audit.call('DELETE', '')
    if any(r.get('outcome') == 'harness_error' for r in results):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
