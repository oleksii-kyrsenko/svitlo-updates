import unittest,sys,pathlib
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from coverage import parse_roster,parse_houses
from discovery import relevant
from history import telegram_page
class Coverage(unittest.TestCase):
 def test_selector_preserves_range_parity_and_exclusions(self):
  self.assertEqual(parse_houses('1–25 (непарні), 12А, крім 13')['excludedHouses'],['13']);self.assertIsNone(parse_houses('1–25 частково'));self.assertIsNone(parse_houses('25–1'))
 def test_roster_cannot_leak_between_localities_or_ignore_exceptions(self):
  html='<meta property="article:published_time" content="2026-10-25T12:00:00+03:00"><article><h3>3 черга 2 підчерга</h3><p>м. Тестове. вул.Садова, 1-25, крім 12; с.Інше вул.Нова, 1-25</p><h3>4 черга 1 підчерга</h3><p>м.Тестове. вул.Миру, 2-20</p></article>'
  import datetime
  now=int(datetime.datetime(2026,10,28,tzinfo=datetime.timezone.utc).timestamp()*1000);source={'url':'https://example.invalid/qa','operatorId':'poltava','regionId':'UA-53','community':'Тестова','settlement':'Тестове'};records=parse_roster(html,source,now)
  self.assertEqual([(r['street'],r['queue']) for r in records],[('вулиця Миру','4.1')])
 def test_unrelated_search_results_do_not_become_sources(self):
  self.assertFalse(relevant('Music radio','https://pandora.com',['Стрижавка']));self.assertFalse(relevant('Стрийська рада','https://example.invalid',['Стрижавська']));self.assertTrue(relevant('Стрижавська громада','https://example.invalid',['Стрижавська']))
 def test_telegram_dates_are_per_publication(self):
  html='<title>Контроль</title><div class="tgme_widget_message_wrap"><div data-post="control/1"><div class="tgme_widget_message_text">Текст</div><time datetime="2026-10-25T12:00:00Z"></time></div></div>'
  title,m=telegram_page(html,'https://t.me/s/control',1793190000000);self.assertEqual(m[0]['sourceUrl'],'https://t.me/control/1');self.assertEqual(len(m),1)
if __name__=='__main__':unittest.main()
