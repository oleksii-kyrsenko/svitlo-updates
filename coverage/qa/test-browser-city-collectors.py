import importlib.util
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
spec = importlib.util.spec_from_file_location('browser_city_test', Path(__file__).resolve().parents[1] / 'browser-city-collectors.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
GEO = {'regionId': 'UA-73', 'settlement': 'Навчальне', 'community': 'Навчальна міська громада'}
SOURCE = 'https://example.org/shutdowns/'


def page(rows, title='Навчальне'):
    return '<title>' + title + ' / Пошук групи</title>' + ''.join(
        '<div><p>' + street + '</p><b>буд.' + house + '</b><u>' + queue + '</u></div>' for street, house, queue in rows)


class BrowserCityControls(unittest.TestCase):
    def test_official_directory_link_must_be_unique_and_same_host(self):
        self.assertEqual(m.branch_link('<a href="../shutdowns-search/">Довідник</a>', SOURCE), 'https://example.org/shutdowns-search/')
        for body in ['<a href="https://evil.example/shutdowns-search/">Довідник</a>',
                     '<a href="/shutdowns-search/1/">Обхід селектора</a>']:
            with self.assertRaises(ValueError):m.branch_link(body, SOURCE)

    def test_city_branch_comes_from_exact_official_selector_and_source_base(self):
        body='<meta property="og:url" content="https://example.org/shutdowns-search/"><select name="diln"><option disabled value="0">Оберіть</option><option value="51">НАВЧАЛЬНЕ</option><option value="52">Інше</option></select>'
        branch,url=m.branch_for_target(body,SOURCE,GEO)
        self.assertEqual(branch['id'],'51');self.assertEqual(url,'https://example.org/shutdowns-search/51/')
        for changed in [body.replace('НАВЧАЛЬНЕ','Інше'),body.replace('https://example.org','https://evil.example'),body.replace('</select>','<option value="53">Навчальне</option></select>')]:
            with self.assertRaises(ValueError):m.branch_for_target(changed,SOURCE,GEO)

    def test_literal_house_boundaries_are_not_collapsed_or_expanded(self):
        self.assertEqual(m.house_key('1-А'),m.house_key('1A'))
        self.assertNotEqual(m.house_key('1/2'),m.house_key('12'))
        self.assertIsNone(m.literal_house('1-9'))
        self.assertEqual(m.literal_house('13/2'),'13/2')
        self.assertEqual(m.literal_house('13-Б'),'13-Б')

    def test_only_target_city_source_rows_are_candidates(self):
        first=m.roster_claims(page([('вул. Нова','1','2')]),'51',GEO)
        self.assertEqual(len(first),1)
        with self.assertRaises(ValueError):m.roster_claims(page([('вул. Нова','1','2')],'Інше'),'51',GEO)

    def test_every_published_house_requires_two_actual_matching_source_reads(self):
        first=m.roster_claims(page([('вул. Нова','1','2'),('вул. Нова','2-А','3')]),'51',GEO)
        second=m.roster_claims(page([('вул. Нова','1','2'),('вул. Нова','2A','3')]),'51',GEO)
        rows,observed,conflicts=m.compare_rosters(first,second,GEO,'https://example.org/source','51',1000)
        self.assertEqual([r['queue'] for r in rows],['2','3']);self.assertEqual(len(observed),2);self.assertEqual(conflicts,0)
        self.assertTrue(all(r['official'] and r['checkedAt']==1000 and r['expiresAt']==86401000 for r in rows))
        self.assertTrue(all(set(r)<=set(['id','regionId','settlement','community','street','scope','houses','queue','sourceUrl','quote','quoteType','checkedAt','expiresAt','official','officialCityId']) for r in rows))

    def test_changed_missing_and_mixed_connections_remain_unconfirmed(self):
        first=m.roster_claims(page([('вул. Нова','1','2'),('вул. Нова','2','3'),('вул. Нова','3','3'),('вул. Нова','3','4')]),'51',GEO)
        second=m.roster_claims(page([('вул. Нова','1','4'),('вул. Нова','3','3'),('вул. Нова','3','4')]),'51',GEO)
        rows,observed,conflicts=m.compare_rosters(first,second,GEO,'https://example.org/source','51',1000)
        self.assertEqual(rows,[]);self.assertEqual(len(observed),3);self.assertEqual(conflicts,3)

    def test_zero_unknown_queue_never_becomes_official(self):
        one=m.roster_claims(page([('вул. Нова','1','0')]),'51',GEO)
        rows,observed,conflicts=m.compare_rosters(one,one,GEO,'https://example.org/source','51',1000)
        self.assertEqual(rows,[]);self.assertEqual(conflicts,1);self.assertEqual(len(observed),1)

    def test_public_script_evidence_requires_official_parent_linked_operator_frame(self):
        class Locator:
            def evaluate_all(self,script):return ['https://interruptions.energy.cn.ua/','https://thirdparty.example/']
        class Page:
            def locator(self,selector):return Locator()
            def content(self):return '<iframe src="https://interruptions.energy.cn.ua/"></iframe>'
        class Response:
            def __init__(self,url):self.url=url;self.status=200
            def body(self):return b'const endpoint="list_acc";'
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            result=m.research_chernihiv(Page(),'https://chernihivoblenergo.com.ua/blackouts',Path(temp),[
                Response('https://interruptions.energy.cn.ua/static/interruptions.js'),
                Response('https://thirdparty.example/static/interruptions.js'),
                Response('https://chernihivoblenergo.com.ua/account.js')])
        self.assertEqual(len(result['publicScripts']),1);self.assertEqual(result['records'],0)
        self.assertFalse(result['queueIntegrationVerified']);self.assertEqual(result['publicScripts'][0]['sourceLinkedFrame'],'https://interruptions.energy.cn.ua/')

    def test_current_gpv_link_requires_active_official_parent_not_archive_or_other_product(self):
        source='https://chernihivoblenergo.com.ua/blackouts'
        good='<h1>Перерви</h1><a href="/files/other/current.pdf">Графік погодинних відключень (ГПВ)</a>'
        self.assertEqual(m.current_roster_link(good,source)['sourceUrl'],'https://chernihivoblenergo.com.ua/files/other/current.pdf')
        cases=[good.replace('ГПВ','ГАВ'),good.replace('<h1>Перерви</h1>','<h1>Архів</h1>'),
               '<div class="archive">'+good+'</div>',good.replace('ГПВ','ГПВ діяв до01.01.2026'),
               good.replace('/files/other/current.pdf','https://thirdparty.example/current.pdf'),
               good+'<a href="/files/other/replacement.pdf">ГПВ</a>']
        for changed in cases:
            with self.assertRaises(ValueError):m.current_roster_link(changed,source)


    def test_failed_fresh_browser_read_cannot_reuse_an_old_candidate(self):
        import tempfile
        from unittest.mock import patch
        class Page:
            def on(self,*args):pass
            def goto(self,*args,**kwargs):raise m.BROWSER.SourceStop('source-protection-interstitial')
        class Context:
            def new_page(self):return Page()
            def close(self):pass
        class Browser:
            def new_context(self,**kwargs):return Context()
            def close(self):pass
        class Engine:
            chromium=type('Chromium',(),{'launch':lambda self:Browser()})()
            def __enter__(self):return self
            def __exit__(self,*args):pass
        with tempfile.TemporaryDirectory() as temp:
            old=Path(temp)/'chernivtsi'/'normalized-candidates.json';old.parent.mkdir();old.write_text('{"records":["old"]}')
            with patch('request_budget.throttle'),patch.object(m.BROWSER,'page_artifacts',return_value={}):
                result=m.run(['chernivtsi'],temp,4,playwright_factory=Engine)
            self.assertFalse(old.exists());self.assertEqual(result['operators'][0]['status'],'stopped-source-protection-interstitial')


if __name__=='__main__':unittest.main()
