"""Visible input/async-directory controls; no application imports or emulator."""
import importlib.util,pathlib,tempfile,unittest,json,sqlite3,shutil,hashlib,copy
from unittest.mock import patch
from xml.sax.saxutils import escape

p=pathlib.Path(__file__).with_name('national-address-audit.py')
s=importlib.util.spec_from_file_location('address_audit_input',p);audit=importlib.util.module_from_spec(s);s.loader.exec_module(audit)


def tree(value='василя аксенина',clear=False,loading=True,option=None):
    rows=['<hierarchy><node class="android.view.View" content-desc="Закрити список адрес" clickable="true" bounds="[0,0][50,50]"/>',
          '<node class="android.widget.EditText" content-desc="Пошук: Вулиця" resource-id="address-search-input" text="'+escape(value,{'"':'&quot;'})+'" displayed="true"/>']
    if clear:rows.append('<node class="android.widget.Button" content-desc="Очистити пошук" resource-id="address-search-input-clear" clickable="true" bounds="[50,0][100,50]"/>')
    if loading:rows.append('<node class="android.view.View" content-desc="Завантаження" resource-id="ui-loader" clickable="false"/>')
    if option:rows.append('<node class="android.widget.Button" content-desc="'+escape(option,{'"':'&quot;'})+'" clickable="true" bounds="[0,100][400,150]"/>')
    return ''.join(rows)+'</hierarchy>'


class Clock:
    def __init__(self):self.now=0
    def monotonic(self):return self.now
    def sleep(self,seconds):self.now+=seconds


class InputAudit(audit.Audit):
    def __init__(self,clock,delay=12,bad=False):
        self.clock=clock;self.delay=delay;self.bad=bad;self.native='';self.calls=[];self.input_retries=[]
    def source(self):return tree(self.native,clear=bool(self.native) and self.clock.now>=self.delay,loading=self.clock.now<self.delay)
    def call(self,method,path,data=None):
        self.calls.append((method,path,data))
        if path=='/element':return {audit.EID:'input-element'}
        if path=='/execute/sync' and data['script']=='mobile: replaceElementValue':self.native='encoded transport' if self.bad else data['args'][0]['text']
        if path.endswith('/clear'):self.native=''
    def screenshot(self,name,xml=None):return xml or self.source()
    def adb(self,*args,**kwargs):
        if self.bad:self.native='encoded transport'
        return ''


class SearchInputControls(unittest.TestCase):
    def post_save_fixture(self,clock):
        case={'city':'Зразок','exactStreet':'вулиця Нова','exactHouse':'7-А'}
        place={'id':'app-active','addressOrigin':'postal','addressParts':{'settlement':'Зразок','street':'вулиця Нова','house':'7-А'},'addressSelection':{'city':{'id':'city'},'street':{'id':'street'},'house':{'id':'house'}},'queueConfirmed':True,'queueOrigin':'official','queue':'3.1'}
        state={'activePlaceId':place['id'],'places':[place]};result={'visibleQueue':None,'addressFromUI':'Зразок, вулиця Нова, 7-А','preSaveObservation':{'outcome':'source_protected','visibleQueue':None,'screenshot':'queue-result.png'}}
        class PostSaveAudit(audit.Audit):
            def __init__(self):self.state=copy.deepcopy(state);self.visible_address=result['addressFromUI'];self.show_queue=True;self.source_reads=0;self.state_reads=0;self.screens=[]
            def source(self):
                self.source_reads+=1
                body='<node resource-id="current-address-name" text="'+escape(self.visible_address)+'"/>'
                if clock.now<.5:body+='<node text="Шукаємо чергу за офіційною адресою…"/>'
                elif self.show_queue:body+='<node text="Черга 3.1"/>'
                return '<hierarchy>'+body+'</hierarchy>'
            def read_state(self):self.state_reads+=1;return self.state
            def screenshot(self,name,xml=None):self.screens.append((name,xml))
        return PostSaveAudit(),case,result,state,place

    def test_late_official_queue_requires_visible_current_home_and_a_fresh_snapshot(self):
        clock=Clock();driver,case,result,state,place=self.post_save_fixture(clock)
        with patch.object(audit.time,'monotonic',clock.monotonic),patch.object(audit.time,'sleep',clock.sleep):
            fresh,selected=driver.observe_post_save_queue(case,result,state,place,2)
        self.assertEqual(selected['queue'],'3.1');self.assertEqual(fresh['activePlaceId'],'app-active');self.assertEqual(driver.state_reads,1)
        self.assertEqual(result['visibleQueue'],'3.1');self.assertEqual(result['visibleQueueStage'],'post-save-home');self.assertEqual(result['preSaveObservation']['outcome'],'source_protected');self.assertIsNone(result['preSaveObservation']['visibleQueue'])
        self.assertTrue(result['postSaveObservation']['pendingSeen']);self.assertLess(clock.now,2);self.assertEqual(driver.screens[0][0],'post-save-queue')

    def test_late_queue_on_another_visible_address_or_changed_active_id_is_rejected(self):
        for changed in ['visible','active']:
            clock=Clock();driver,case,result,state,place=self.post_save_fixture(clock)
            if changed=='visible':driver.visible_address='Зразок, вулиця Інша, 7-А'
            else:driver.state['activePlaceId']='another-address'
            with patch.object(audit.time,'monotonic',clock.monotonic),patch.object(audit.time,'sleep',clock.sleep):
                with self.assertRaisesRegex(RuntimeError,'address'):driver.observe_post_save_queue(case,result,state,place,2)
            self.assertIsNone(result['visibleQueue'])

    def test_state_only_queue_and_exhausted_original_deadline_never_become_visible_success(self):
        for deadline in [0,1]:
            clock=Clock();driver,case,result,state,place=self.post_save_fixture(clock);driver.show_queue=False
            with patch.object(audit.time,'monotonic',clock.monotonic),patch.object(audit.time,'sleep',clock.sleep):
                with self.assertRaisesRegex(RuntimeError,'original queue deadline exhausted'):driver.observe_post_save_queue(case,result,state,place,deadline)
            self.assertEqual(driver.state_reads,0);self.assertIsNone(result['visibleQueue']);self.assertLessEqual(clock.now,deadline)
            if deadline==0:self.assertEqual(driver.source_reads,0)

    def test_an_earlier_visible_queue_mismatch_and_nonofficial_state_are_not_forgiven(self):
        clock=Clock();driver,case,result,state,place=self.post_save_fixture(clock);result['visibleQueue']='2.1'
        with self.assertRaisesRegex(RuntimeError,'earlier visible queue mismatch'):driver.observe_post_save_queue(case,result,state,place,200)
        result['visibleQueue']=None;place['queueOrigin']='public'
        with self.assertRaisesRegex(RuntimeError,'confirmed official'):driver.observe_post_save_queue(case,result,state,place,200)
        self.assertEqual(driver.source_reads,0)

    def test_a_source_response_after_the_original_deadline_does_not_count(self):
        clock=Clock();driver,case,result,state,place=self.post_save_fixture(clock)
        source=driver.source
        def delayed():clock.now+=2;return source()
        driver.source=delayed
        with patch.object(audit.time,'monotonic',clock.monotonic),patch.object(audit.time,'sleep',clock.sleep):
            with self.assertRaisesRegex(RuntimeError,'original queue deadline exhausted'):driver.observe_post_save_queue(case,result,state,place,1)
        self.assertIsNone(result['visibleQueue']);self.assertEqual(driver.state_reads,0)

    def test_actual_editor_pending_caption_prevents_an_early_save(self):
        for caption in ['Перевіряємо чергу за адресою…', 'Шукаємо чергу за адресою…',
                        'Чергу ще перевіряємо. Адресу вже можна зберегти.']:
            self.assertTrue(audit.queue_lookup_pending('Будинок 8 '+caption))
        for caption in ['Черга 2.1 · знайдено автоматично', 'Чергу не знайдено',
                        'Уточніть підключення', 'Джерело тимчасово недоступне']:
            self.assertFalse(audit.queue_lookup_pending(caption))
    def state_capture_driver(self,folder):
        source=folder/'source';source.mkdir();database=source/'RKStorage'
        with sqlite3.connect(database) as connection:
            connection.execute('CREATE TABLE catalystLocalStorage (key TEXT PRIMARY KEY,value TEXT)')
            connection.execute('INSERT INTO catalystLocalStorage VALUES (?,?)',('svitlo.state.v1',json.dumps({'activePlaceId':'app-written','places':[]})))
        class CaptureAudit(audit.Audit):
            def __init__(self):self.case_dir=folder/'case';self.pulls=[]
            def adb(self,*args,**kwargs):
                assert args[:2]==('pull','/data/data/'+audit.PKG+'/databases')
                target=pathlib.Path(args[2])/'databases';target.mkdir();shutil.copy2(database,target/'RKStorage')
                if not self.pulls:(target/'RKStorage-journal').write_bytes(b'first captured journal')
                self.pulls.append(target);return ''
        return CaptureAudit()

    def test_live_hot_journal_retries_a_distinct_readonly_capture_and_retains_originals(self):
        with tempfile.TemporaryDirectory() as temp:
            driver=self.state_capture_driver(pathlib.Path(temp));connect=sqlite3.connect;calls=[]
            def reader(location,**kwargs):
                calls.append(location);self.assertTrue(location.endswith('?mode=ro'));self.assertTrue(kwargs['uri'])
                if len(calls)==1:raise sqlite3.OperationalError('attempt to write a readonly database')
                return connect(location,**kwargs)
            with patch.object(audit.sqlite3,'connect',reader),patch.object(audit.time,'sleep'):
                self.assertEqual(driver.read_state(),{'activePlaceId':'app-written','places':[]})
            self.assertEqual(len(driver.pulls),2);self.assertNotEqual(driver.pulls[0],driver.pulls[1]);self.assertTrue((driver.pulls[0]/'RKStorage-journal').exists());self.assertFalse((driver.pulls[1]/'RKStorage-journal').exists())
            proof=json.loads((driver.pulls[0].parent/'capture.json').read_text());self.assertEqual(proof['captureError'],'sqlite-readonly-hot-journal-recovery')
            original=next(x for x in proof['files'] if x['path'].endswith('RKStorage-journal'));self.assertEqual(original['sha256'],hashlib.sha256(b'first captured journal').hexdigest())

    def test_hot_journal_capture_retries_are_bounded_and_other_sqlite_errors_are_not_hidden(self):
        for error,count in [('attempt to write a readonly database',3),('database disk image is malformed',1)]:
            with tempfile.TemporaryDirectory() as temp:
                driver=self.state_capture_driver(pathlib.Path(temp))
                with patch.object(audit.sqlite3,'connect',side_effect=sqlite3.OperationalError(error)),patch.object(audit.time,'sleep'):
                    with self.assertRaisesRegex(sqlite3.OperationalError,error):driver.read_state()
                self.assertEqual(len(driver.pulls),count)

    def test_selection_transition_completed_in_retry_tree_is_accepted_without_another_tap(self):
        # Actual UA-18-capital-1: the 2s wait saw the list, but the next tree
        # already showed the editor and selected street. Old code treated the
        # correctly absent option as a failed selection.
        class SelectionAudit(audit.Audit):
            def __init__(self):self.taps=0;self.reads=0
            def click_node(self,node):self.taps+=1
            def wait(self,predicate,seconds):
                self.asserted_seconds=seconds
                raise RuntimeError('transition still visible in final bounded observation')
            def source(self):self.reads+=1;return '<hierarchy><node content-desc="Обрати: Вулиця" text="вулиця Зразкова"/></hierarchy>'
            def options(self,xml):raise AssertionError('Closed list must not be searched or tapped again')
        driver=SelectionAudit();driver.choose_option(audit.ET.fromstring('<node content-desc="вулиця Зразкова"/>'))
        self.assertEqual((driver.taps,driver.reads,driver.asserted_seconds),(1,1,2))

    def test_missing_option_in_a_still_open_list_remains_a_failure(self):
        class SelectionAudit(audit.Audit):
            def __init__(self):pass
            def click_node(self,node):pass
            def wait(self,predicate,seconds):raise RuntimeError('still open')
            def source(self):return tree(option='вулиця Інша')
        with self.assertRaisesRegex(RuntimeError,'Selected address option did not close'):
            SelectionAudit().choose_option(audit.ET.fromstring('<node content-desc="вулиця Зразкова"/>'))

    def test_menu_transition_does_not_reuse_the_previous_home_tree(self):
        # Actual UA-68-capital-5 failure: the cached tree still mentioned the
        # home menu button, while the current screen already showed its menu.
        clock=Clock()
        class NavigationAudit(audit.Audit):
            def __init__(self):self.stage='home';self.add_checks=0;self.actions=[]
            def source(self):
                return {'home':'<hierarchy><node resource-id="app-menu-button"/></hierarchy>',
                        'menu':'<hierarchy><node content-desc="Додати адресу"/></hierarchy>',
                        'editor':'<hierarchy><node content-desc="Обрати: Область"/></hierarchy>'}[self.stage]
            def tap(self,label,scroll=False,required=True):
                self.actions.append(label)
                if label=='Додати адресу':
                    self.add_checks+=1
                    if self.add_checks==1:self.stage='menu';return False
                    self.stage='editor';return True
                if label=='app-menu-button':raise RuntimeError('cached home button is unavailable')
                return False
            def wait(self,predicate,seconds=25):
                xml=self.source()
                if not predicate(xml):raise RuntimeError('did not open the empty editor')
                return xml
        driver=NavigationAudit()
        with patch.object(audit.time,'sleep',clock.sleep):driver.open_new_editor()
        self.assertEqual(driver.stage,'editor');self.assertNotIn('app-menu-button',driver.actions)
    def test_native_text_and_custom_loader_do_not_fake_react_commit(self):
        # Actual failed Chernivtsi shape: the text is present, custom loader is
        # visible, and the app-owned Clear control has not rendered yet.
        state=audit.search_input_state(tree(),'Вулиця','василя аксенина')
        self.assertTrue(state['nativeMatches']);self.assertTrue(state['loading']);self.assertFalse(state['committed'])
    def test_long_directory_boot_does_not_retype_an_already_pending_value(self):
        clock=Clock();driver=InputAudit(clock,delay=12)
        with patch.object(audit.time,'monotonic',clock.monotonic),patch.object(audit.time,'sleep',clock.sleep):driver.type_search('Вулиця','василя аксенина')
        replacements=[d for _,_,d in driver.calls if d and d.get('script')=='mobile: replaceElementValue']
        self.assertEqual(len(replacements),1);self.assertEqual(driver.input_retries,[]);self.assertGreaterEqual(clock.now,12)
    def test_uncommitted_native_value_is_still_a_failure_after_bounded_wait(self):
        clock=Clock();driver=InputAudit(clock,delay=1000);driver.native='василя аксенина'
        with patch.object(audit.time,'monotonic',clock.monotonic),patch.object(audit.time,'sleep',clock.sleep):
            self.assertRaisesRegex(RuntimeError,'not committed',driver.wait_search_commit,'Вулиця','василя аксенина',6,10)
        self.assertGreaterEqual(clock.now,10);self.assertLess(clock.now,11)
    def test_permanently_busy_app_is_not_retyped_three_times(self):
        clock=Clock();driver=InputAudit(clock,delay=1000)
        with patch.object(audit.time,'monotonic',clock.monotonic),patch.object(audit.time,'sleep',clock.sleep):self.assertRaises(audit.SearchInputNotCommitted,driver.type_search,'Вулиця','василя аксенина')
        replacements=[d for _,_,d in driver.calls if d and d.get('script')=='mobile: replaceElementValue']
        self.assertEqual(len(replacements),1);self.assertLess(clock.now,47)
    def test_wrong_unicode_transport_is_not_accepted_or_hidden_by_loader(self):
        clock=Clock();driver=InputAudit(clock,delay=1000,bad=True)
        with patch.object(audit.time,'monotonic',clock.monotonic),patch.object(audit.time,'sleep',clock.sleep):self.assertRaisesRegex(RuntimeError,'did not accept',driver.type_search,'Вулиця','василя аксенина')
        self.assertEqual(len(driver.input_retries),3);self.assertLess(clock.now,30)
    def test_empty_search_requires_the_actual_visible_input_to_be_empty(self):
        self.assertFalse(audit.search_input_state(tree('old query'),'Вулиця','')['committed'])
        self.assertTrue(audit.search_input_state(tree(''),'Вулиця','')['committed'])
    def test_loading_timeout_is_a_source_outcome_not_a_false_empty_directory(self):
        clock=Clock();driver=InputAudit(clock);driver.current_field='Вулиця';driver.current_query='василя аксенина';driver.source=lambda:tree(clear=True,loading=True)
        with patch.object(audit.time,'monotonic',clock.monotonic),patch.object(audit.time,'sleep',clock.sleep):self.assertRaises(audit.AddressSearchTimeout,driver.wait_options,3)
    def test_matching_official_option_remains_selectable_while_postal_loading(self):
        clock=Clock();driver=InputAudit(clock);driver.current_field='Вулиця';driver.current_query='василя аксенина';driver.source=lambda:tree(clear=True,loading=True,option='вулиця Василя Аксенина · довідник оператора')
        with patch.object(audit.time,'monotonic',clock.monotonic),patch.object(audit.time,'sleep',clock.sleep):options,_=driver.wait_options(3)
        self.assertEqual(len(options),1);self.assertEqual(clock.now,0)
    def test_pending_source_result_is_retained_without_counting_queue_or_harness_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            driver=InputAudit(Clock());driver.out=pathlib.Path(tmp);driver.contract={**audit.audit_contract.DEFAULT,'sampleSha256':'0'*64};driver.installed_apk_sha256=driver.contract['apkSha256'];driver.current_field='Вулиця';driver.current_query='василя аксенина'
            xml=tree(clear=True,loading=True)
            def pending():raise audit.AddressSearchTimeout('Вулиця',xml)
            driver.open_new_editor=pending
            result=driver.run_case({'id':'synthetic-failure','city':'Навчальне'})
            self.assertEqual(result['outcome'],'address_source_timeout');self.assertNotIn('visibleQueue',result);self.assertNotIn('automationError',result)
            self.assertEqual((driver.case_dir/'address-source-timeout.xml').read_text(),xml)
    def test_cached_option_cannot_hide_a_query_that_changed_after_typing(self):
        driver=InputAudit(Clock());driver.current_field='Вулиця';driver.current_query='василя аксенина';driver.source=lambda:tree('інша',clear=True,loading=False,option='вулиця Василя Аксенина')
        self.assertRaisesRegex(RuntimeError,'changed after typing',driver.wait_options,1)


class SourceBoundRenames(unittest.TestCase):
    def fixture(self):
        case={'id':'synthetic-rename','city':'Зразок','regionId':'UA-99','exactStreet':'вулиця Стара','exactHouse':'7-А'}
        city={'REGION_ID':'299','DISTRICT_ID':'9','CITY_ID':'123','CITY_KATOTTG':'12345678901234567','CITY_UA':'Зразок'}
        street={**{k:city[k] for k in ['REGION_ID','DISTRICT_ID','CITY_ID']},'STREET_ID':'55','STREET_UA':'Нова','STREETTYPE_UA':'вулиця','OLDSTREET_UA':'Стара'}
        city_label='м. Зразок · Громада · КАТОТТГ '+city['CITY_KATOTTG'];label='вулиця Нова · раніше Стара'
        result={'selectedCityLabel':city_label,'selectedStreetLabel':label}
        place={'regionId':'UA-99','addressOrigin':'postal','addressParts':{'settlement':'Зразок','street':'вулиця Нова','house':'7-А'},'addressSelection':{'region':{'id':'UA-99'},'city':{'id':'123','postalId':'299','districtId':'9','katottg':city['CITY_KATOTTG'],'label':city_label},'street':{'id':'55','name':'вулиця Нова','registryName':'Нова','registryType':'вулиця','oldName':'Стара','label':label},'house':{'id':'55:7-А:12345'}}}
        return case,result,place,city,street

    def captured(self,temp,city,streets):
        records=[city] if isinstance(city,dict) else city
        bodies=[json.dumps({'Entries':{'Entry':records}},ensure_ascii=False).encode(),json.dumps({'Entries':{'Entry':streets}},ensure_ascii=False).encode()]
        calls=[]
        class Response:
            status=200
            def __init__(self,url,body):self.url=url;self.body=body
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def read(self,bound):assert bound==4000001;return self.body
        def reader(request,timeout):
            self.assertEqual(timeout,25);calls.append(request.full_url)
            return Response(request.full_url,bodies[len(calls)-1])
        return bodies,calls,reader

    def proof(self,temp):
        case,result,place,city,street=self.fixture();bodies,calls,reader=self.captured(temp,city,[street])
        with patch.object(audit.urllib.request,'urlopen',reader):result['selectedPostalRenameIdentity']=audit.capture_postal_rename_identity(case,result,result['selectedStreetLabel'],temp)
        return case,result,place,bodies,calls

    def test_source_read_before_click_binds_unique_city_street_id_and_keeps_original_bodies(self):
        with tempfile.TemporaryDirectory() as temp:
            case,result,place,bodies,calls=self.proof(pathlib.Path(temp))
            self.assertEqual(len(calls),2);audit.validate_saved_address(case,result,place)
            for index,evidence in enumerate(result['selectedPostalRenameIdentity']['responses']):
                original=(pathlib.Path(temp)/evidence['artifact']).read_bytes();self.assertEqual(original,bodies[index]);self.assertEqual(hashlib.sha256(original).hexdigest(),evidence['sha256'])
            self.assertEqual(result['selectedPostalRenameIdentity']['street']['STREET_ID'],'55')

    def test_current_name_selection_needs_no_extra_request_and_arbitrary_saved_old_name_cannot_prove_rename(self):
        case,result,place,_,_=self.fixture()
        with patch.object(audit.urllib.request,'urlopen',side_effect=AssertionError('No read for ordinary current name')):
            current={**case,'exactStreet':'вулиця Нова'}
            self.assertIsNone(audit.capture_postal_rename_identity(current,result,result['selectedStreetLabel'],pathlib.Path('/unused')))
        with self.assertRaisesRegex(RuntimeError,'Saved street/type differs'):audit.validate_saved_address(case,result,place)

    def test_other_id_locality_current_name_alias_or_visible_label_cannot_borrow_valid_source_proof(self):
        with tempfile.TemporaryDirectory() as temp:
            case,result,place,_,_=self.proof(pathlib.Path(temp))
            changes=[lambda p:p['addressSelection']['street'].update(id='56'),lambda p:p['addressSelection']['city'].update(id='999'),lambda p:p['addressSelection']['city'].update(katottg='98765432109876543'),lambda p:p['addressSelection']['street'].update(oldName='Інша'),lambda p:p['addressSelection']['street'].update(registryName='Інша'),lambda p:p['addressSelection']['street'].update(label='вулиця Інша · раніше Стара'),lambda p:p.update(regionId='UA-98'),lambda p:p['addressParts'].update(street='провулок Нова')]
            for change in changes:
                changed=copy.deepcopy(place);change(changed)
                with self.assertRaisesRegex(RuntimeError,'Saved street/type differs'):audit.validate_saved_address(case,result,changed)

    def test_rename_proof_does_not_drop_road_type_or_house_letter_and_rejects_unrelated_source_query(self):
        with tempfile.TemporaryDirectory() as temp:
            case,result,place,_,_=self.proof(pathlib.Path(temp))
            for target in [{**case,'exactStreet':'провулок Стара'},{**case,'exactHouse':'7'}]:
                with self.assertRaises(RuntimeError):audit.validate_saved_address(target,result,place)
            result['selectedPostalRenameIdentity']['responses'][1]['url']=audit.POSTAL_API+'?method=unrelated'
            with self.assertRaisesRegex(RuntimeError,'Saved street/type differs'):audit.validate_saved_address(case,result,place)

    def test_ambiguous_independent_city_or_street_rows_fail_without_selecting_an_id(self):
        for ambiguous in ['city','street']:
            with tempfile.TemporaryDirectory() as temp:
                case,result,place,city,street=self.fixture();cities=[city,copy.deepcopy(city)] if ambiguous=='city' else city
                streets=[street,{**street,'STREET_ID':'56'}] if ambiguous=='street' else [street]
                _,_,reader=self.captured(pathlib.Path(temp),cities,streets)
                with patch.object(audit.urllib.request,'urlopen',reader):
                    with self.assertRaisesRegex(RuntimeError,'not unique|not a unique'):audit.capture_postal_rename_identity(case,result,result['selectedStreetLabel'],pathlib.Path(temp))


class SelectionMissingElementRace(unittest.TestCase):
    def driver(self,closed,initial_missing=False,error_kind='no such element'):
        class SelectionAudit(audit.Audit):
            def __init__(self):self.current_field='Вулиця';self.taps=0;self.reads=0;self.screens=[]
            def click_node(self,node):
                self.taps+=1
                if initial_missing or self.taps==2:raise RuntimeError(json.dumps({'value':{'error':error_kind}}))
            def wait(self,predicate,seconds):
                assert seconds==2
                raise RuntimeError('final transition observation still showed list')
            def source(self):
                self.reads+=1
                return tree(option='вулиця Зразкова') if self.reads==1 and not initial_missing else closed
            def screenshot(self,name,xml=None):self.screens.append((name,xml))
        return SelectionAudit()

    def closed(self,value='вулиця Зразкова'):
        return '<hierarchy><node content-desc="Обрати: Вулиця" bounds="[0,100][400,150]"><node text="'+value+'"/></node></hierarchy>'

    def test_successful_click_then_missing_retry_requires_closed_editor_with_exact_selected_field(self):
        driver=self.driver(self.closed());driver.choose_option(audit.ET.fromstring('<node content-desc="вулиця Зразкова"/>'))
        self.assertEqual(driver.taps,2);self.assertEqual(driver.reads,2);self.assertEqual(driver.screens[0][0],'selected-street-transition-confirmed')

    def test_wrong_selected_road_absent_field_or_still_open_modal_never_forgives_missing_retry(self):
        for closed in [self.closed('вулиця Інша'),self.closed('провулок Зразкова'),'<hierarchy/>',tree(option='вулиця Зразкова')]:
            driver=self.driver(closed)
            with self.assertRaisesRegex(RuntimeError,'no such element'):driver.choose_option(audit.ET.fromstring('<node content-desc="вулиця Зразкова"/>'))
            self.assertEqual(driver.screens,[])

    def test_first_click_missing_or_other_automation_error_is_not_accepted_from_a_matching_editor(self):
        for initial,kind in [(True,'no such element'),(False,'unknown error')]:
            driver=self.driver(self.closed(),initial_missing=initial,error_kind=kind)
            with self.assertRaisesRegex(RuntimeError,kind):driver.choose_option(audit.ET.fromstring('<node content-desc="вулиця Зразкова"/>'))
            self.assertEqual(driver.screens,[])


if __name__=='__main__':unittest.main()
