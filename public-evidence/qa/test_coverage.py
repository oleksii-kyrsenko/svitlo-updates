import unittest,sys,pathlib
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from coverage import parse_roster,parse_houses,published_at
from documents import document_links,watch_documents,inspect_document
from bs4 import BeautifulSoup
from unittest.mock import patch
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
class Documents(unittest.TestCase):
 def test_article_date_does_not_borrow_sidebar_time(self):
  self.assertIsNone(published_at(BeautifulSoup('<footer><time datetime="2026-10-28T12:00:00Z"></time></footer>','html.parser')))
  self.assertEqual(published_at(BeautifulSoup('<time class="content-date" datetime="2026-10-27T21:00:00+02:00"></time>','html.parser')),1793127600000)
 def test_document_links_require_reviewed_hosts_and_public_https(self):
  body='<a href="https://operator.example/current.pdf">Документ</a><a href="https://other.example/old.pdf">Копія</a><a href="https://u:p@operator.example/private.pdf">Логін</a><a href="http://operator.example/current.pdf">HTTP</a><a href="https://operator.example:8443/current.pdf">Port</a>'
  self.assertEqual([r['url'] for r in document_links(body,'https://news.example/', ['operator.example'])],['https://operator.example/current.pdf'])
 def test_link_date_does_not_renew_or_activate_document(self):
  now=1793190000000;url='https://news.example/article';doc='https://operator.example/old.pdf'
  body='<time class="content-date" datetime="2026-10-27T21:00:00+02:00"></time><article><a href="'+doc+'">Графік</a></article>'
  def fetch(u):return (body.encode(),'text/html',url) if u==url else (b'%PDF-old','application/pdf',doc)
  with patch('documents.inspect_document',return_value={'format':'pdf','pages':1,'textCharacters':100}):
   report=watch_documents({'url':url,'operatorId':'poltava','regionId':'UA-53','documentHosts':['operator.example']},fetch,now)
  self.assertEqual(report['runtimeRecords'],0);self.assertEqual(report['documents'][0]['status'],'needs_document_review');self.assertIsNone(report['documents'][0]['documentPublishedAt']);self.assertNotIn('publishedAt',report['documents'][0])
 def test_bad_document_body_and_fetch_failure_are_reported(self):
  with self.assertRaises(ValueError):inspect_document(b'<html>challenge</html>','application/pdf')
  url='https://news.example/article';body=b'<time class="content-date" datetime="2026-10-27T21:00:00+02:00"></time><article><a href="https://operator.example/current.pdf">Doc</a></article>'
  def fetch(u):
   if u==url:return body,'text/html',url
   raise ValueError('source unavailable')
  report=watch_documents({'url':url,'operatorId':'poltava','regionId':'UA-53','documentHosts':['operator.example']},fetch,1793190000000)
  self.assertEqual(report['documents'][0]['status'],'fetch_or_format_error');self.assertIn('unavailable',report['documents'][0]['error']);self.assertEqual(report['runtimeRecords'],0)
 def test_document_limit_deduplicates_repeated_links(self):
  url='https://news.example/article';body='<time class="content-date" datetime="2026-10-27T21:00:00+02:00"></time><article>'+''.join('<a href="https://operator.example/'+str(i//2)+'.pdf">Doc</a>' for i in range(12))+'</article>';calls=[]
  def fetch(u):
   calls.append(u)
   return (body.encode(),'text/html',url) if u==url else (b'%PDF-old','application/pdf',u)
  with patch('documents.inspect_document',return_value={'format':'pdf','pages':1,'textCharacters':1}):
   report=watch_documents({'url':url,'operatorId':'poltava','regionId':'UA-53','documentHosts':['operator.example']},fetch,1793190000000)
  self.assertEqual(len(report['documents']),3);self.assertEqual(len(calls),4)
 def test_operator_landing_is_followed_without_fixed_document_name(self):
  url='https://news.example/article';landing='https://operator.example/disconnection/hrafik/';doc='https://operator.example/current-season.pdf';calls=[]
  body='<time class="content-date" datetime="2026-10-27T21:00:00+02:00"></time><article><a href="'+landing+'">Посилання</a></article>'
  def fetch(u):
   calls.append(u)
   return (body.encode(),'text/html',u) if u==url else (('<a href="'+doc+'">PDF</a>').encode(),'text/html',u) if u==landing else (b'%PDF-test','application/pdf',u)
  with patch('documents.inspect_document',return_value={'format':'pdf','pages':1,'textCharacters':100}):
   report=watch_documents({'url':url,'operatorId':'poltava','regionId':'UA-53','documentHosts':['operator.example']},fetch,1793190000000)
  self.assertEqual(calls,[url,landing,doc]);self.assertEqual(report['documents'][0]['discoveryPath'],[url,landing,doc]);self.assertIsNone(report['documents'][0]['linkedFromPublishedAt']);self.assertIsNone(report['documents'][0]['documentPublishedAt']);self.assertEqual(report['runtimeRecords'],0)
 def test_landing_failure_does_not_claim_document_was_read(self):
  url='https://news.example/article';body=b'<time class="content-date" datetime="2026-10-27T21:00:00+02:00"></time><article><a href="https://operator.example/disconnection/">Graph</a></article>'
  def fetch(u):
   if u==url:return body,'text/html',url
   raise ValueError('503 unavailable')
  report=watch_documents({'url':url,'operatorId':'poltava','regionId':'UA-53','documentHosts':['operator.example']},fetch,1793190000000)
  self.assertEqual(report['documents'],[]);self.assertEqual(report['landingPages'][0]['status'],'fetch_or_format_error');self.assertIn('503',report['landingPages'][0]['error'])
if __name__=='__main__':unittest.main()
