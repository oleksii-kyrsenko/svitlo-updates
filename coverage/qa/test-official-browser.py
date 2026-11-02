import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
spec = importlib.util.spec_from_file_location('official_browser', Path(__file__).resolve().parents[1]/'browser-official.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
SOURCE = 'https://www.example.org/public-address-form'

class Locator:
    def __init__(self, visible=False): self.visible = visible
    def count(self): return 1 if self.visible else 0
    def nth(self, index): return self
    def is_visible(self): return self.visible

class Page:
    url = SOURCE
    def __init__(self, payload=None, selectors=(), body='<form id="public">Ordinary public lookup</form>'):
        self.payload = payload or {'status':200,'url':SOURCE,'body':'[]','bytes':2}
        self.selectors = selectors
        self.body = body
        self.calls = []
    def locator(self, selector): return Locator(selector in self.selectors)
    def content(self): return self.body
    def evaluate(self, javascript, payload):
        self.calls.append(payload)
        assert "redirect:'manual'" in javascript
        assert 'getReader' in javascript
        assert 'controller.abort()' in javascript
        return self.payload

class BrowserControls(unittest.TestCase):
    def setUp(self):
        self.throttle = patch('request_budget.throttle')
        self.throttle.start()
        self.addCleanup(self.throttle.stop)
    def test_official_origins_refuse_credentials_http_other_hosts(self):
        for value in ['http://www.example.org/public','https://user:pass@example.org/public','https://evil.example/public','https://example.org/public#fragment']:
            self.assertFalse(m.same_official_host(value,SOURCE))
        self.assertTrue(m.same_official_host('https://example.org/public',SOURCE))
    def test_visible_challenge_or_login_stops_before_requests(self):
        for selector,reason in [('iframe[src*="challenges.cloudflare.com"]','visible-captcha-or-turnstile'),('input[type="password"]','visible-login-required')]:
            page=Page(selectors=(selector,));http=m.BrowserHTTP(page,None,SOURCE)
            with self.assertRaises(m.SourceStop) as error:http.text(SOURCE)
            self.assertEqual(error.exception.reason,reason);self.assertFalse(page.calls)
    def test_an_invisible_normal_captcha_library_is_not_a_solved_challenge(self):
        page=Page(body='<script src="https://www.google.com/recaptcha/api.js"></script><form>Address</form>')
        self.assertIsNone(m.visible_block(page))
        self.assertEqual(m.raw_block('<title>Just a moment</title><script>cf-chl-token</script>'),'source-protection-interstitial')
    def test_first_public_document_then_actual_browser_fetch(self):
        page=Page();http=m.BrowserHTTP(page,None,SOURCE)
        self.assertEqual(http.text(SOURCE),page.body)
        self.assertEqual(http.json(SOURCE+'/cities?search='),[])
        self.assertEqual(len(page.calls),1)
        self.assertEqual(http.trace[-1]['transport'],'ordinary-chromium-fetch')
        self.assertNotIn('headers',http.trace[-1])
    def test_public_form_state_is_sent_but_not_recorded(self):
        page=Page(payload={'status':200,'url':SOURCE,'body':'{}','bytes':2});http=m.BrowserHTTP(page,None,SOURCE)
        http.json(SOURCE,{'form_build_id':'public-ephemeral-state','city_id':'7'},ajax=True,referer=SOURCE)
        self.assertIn('form_build_id=',page.calls[0]['body'])
        self.assertNotIn('public-ephemeral-state',json.dumps(http.trace))
        self.assertEqual(page.calls[0]['headers']['X-Requested-With'],'XMLHttpRequest')
    def test_subscriber_credential_or_crosshost_request_is_refused(self):
        for fields in [{'accountNumber':'123'},{'eic':''},{'password':'anything'},{'search_type':'1'},{'search_type':'2'}]:
            page=Page();http=m.BrowserHTTP(page,None,SOURCE)
            with self.assertRaisesRegex(m.SourceStop,'subscriber'):http.text(SOURCE,fields)
            self.assertFalse(page.calls)
        page=Page();http=m.BrowserHTTP(page,None,SOURCE)
        with self.assertRaisesRegex(m.SourceStop,'cross-host'):http.text('https://another.org/addresses')
        self.assertFalse(page.calls)
    def test_redirect_protection_and_oversize_cannot_become_data(self):
        for payload,reason in [({'redirectRefused':True},'redirect-refused'),
                ({'status':403,'url':SOURCE,'body':'Denied','bytes':6},'http-403'),
                ({'status':200,'url':SOURCE,'body':'[]','bytes':m.MAX_BODY+1},'response-limit'),
                ({'status':200,'url':'https://evil.example/','body':'[]','bytes':2},'another-host')]:
            page=Page(payload=payload);http=m.BrowserHTTP(page,None,SOURCE)
            with self.assertRaisesRegex(m.SourceStop,reason):http.text(SOURCE,{'city':'7'})
    def test_explicit_request_budget_keeps_the_same_session_bounded(self):
        page=Page();http=m.BrowserHTTP(page,None,SOURCE,limit=1)
        http.text(SOURCE)
        with self.assertRaisesRegex(m.SourceStop,'request-budget'):http.text(SOURCE+'/cities')
        self.assertFalse(page.calls)
    def test_raw_public_response_proof_is_bounded_and_content_addressed(self):
        with tempfile.TemporaryDirectory() as tmp:
            page=Page();http=m.BrowserHTTP(page,None,SOURCE,evidence_directory=tmp)
            http.json(SOURCE+'/autocomplete/read_city?q=')
            original=http.trace[-1]['original'];path=Path(tmp)/original['path']
            self.assertEqual(path.read_bytes(),b'[]');self.assertEqual(m.sha(path.read_bytes()),original['sha256'])
            event={};http.remember_public_body('x'*(m.MAX_ARTIFACT+1),event)
            self.assertEqual(event['originalEvidenceConstraint'],'bounded-source-evidence-limit')
    def test_public_crawl_state_survives_a_failed_source_without_old_record_reuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp);state=directory/'cursor.json'
            class Forms:
                @staticmethod
                def city_key(value):return value.casefold()
                @staticmethod
                def scoped_state(saved,target,full):return saved.setdefault('city',{})
                @staticmethod
                def vinnytsia(http,geo,cursor):
                    cursor['streetIndex']=4;raise m.SourceStop('official-http-403')
            with patch.object(m,'load_forms',return_value=Forms):
                result=m.collect_vinnytsia(Page(),None,SOURCE,directory,10,state_path=state)
            self.assertEqual(json.loads(state.read_text())['city']['streetIndex'],4)
            self.assertEqual(result['records'],0);self.assertNotIn('candidateBundle',result)
    def test_single_collector_keeps_evidence_bundle_and_output_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp)/'evidence';directory.mkdir();destination=Path(tmp)/'out.json'
            class Forms:
                @staticmethod
                def city_key(value):return value.casefold()
                @staticmethod
                def scoped_state(saved,target,full):return saved.setdefault('city',{})
                @staticmethod
                def vinnytsia(http,geo,cursor):return ([{'expiresAt':10000000000000}],[],[],[],{'verifiedHouseFormResponses':1})
            with patch.object(m,'load_forms',return_value=Forms):
                result=m.collect_vinnytsia(Page(),None,SOURCE,directory,10,bundle_path=destination)
            proof=directory/result['candidateBundle']['path']
            self.assertEqual(proof.read_bytes(),destination.read_bytes())
            self.assertEqual(m.sha(destination.read_bytes()),result['candidateBundle']['sha256'])
    def test_diagnostics_drop_queries_cookies_and_headers(self):
        response=type('R',(),{'url':SOURCE+'?token=opaque&house=7','status':200,'headers':{'set-cookie':'private','content-type':'application/json;charset=utf-8'}})()
        self.assertEqual(m.request_summary(response),{'host':'www.example.org','path':'/public-address-form','status':200,'contentType':'application/json'})
    def test_cli_rejects_unreviewed_operator_or_unbounded_budget_before_browser(self):
        for operators,budget in [(['unknown'],10),(['sumy','sumy'],10),(['sumy'],121)]:
            with self.assertRaises(ValueError):m.run(operators,'/tmp/unused-official-browser-test',budget)

if __name__ == '__main__': unittest.main()
