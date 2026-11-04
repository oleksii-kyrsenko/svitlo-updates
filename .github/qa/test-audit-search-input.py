"""Visible input/async-directory controls; no application imports or emulator."""
import importlib.util,pathlib,tempfile,unittest
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


if __name__=='__main__':unittest.main()
