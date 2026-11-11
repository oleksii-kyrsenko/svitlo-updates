import importlib.util,unittest
from unittest.mock import patch
from urllib.parse import unquote,urlsplit
from pathlib import Path
p=Path(__file__).parents[1]/'monitor.py';s=importlib.util.spec_from_file_location('monitor',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Tests(unittest.TestCase):
 def test_challenge_is_not_success(self):self.assertEqual(m.classify(200,'<script src="/cdn-cgi/challenge-platform/"></script>'),'source_protected')
 def test_ok_is_only_availability(self):self.assertEqual(m.classify(200,'page'),'page_available')
 def test_discovery_never_makes_queue(self):
  p=m.Links('https://example.org/');p.feed('<a href="https://t.me/channel">channel</a><a href="/list.pdf">doc</a><a href="javascript:alert(1)">bad</a>');self.assertEqual(len(p.links),2)
 def test_address_portal_iframe_is_a_discovery_lead_only(self):
  p=m.Links('https://example.org/');p.feed('<iframe src="https://portal.example.org/disconnection-by-address"></iframe><iframe src="javascript:alert(1)"></iframe>');self.assertEqual(p.links,['https://portal.example.org/disconnection-by-address'])
 def test_unicode_path_and_query_preserve_url_boundaries_and_existing_escapes(self):
  original='https://example.org/графіки/%D0%B3?місто=Луцьк&path=%2Funchanged&flag=a+b'
  actual=m.request_url(original);actual.encode('ascii')
  self.assertEqual(actual,'https://example.org/%D0%B3%D1%80%D0%B0%D1%84%D1%96%D0%BA%D0%B8/%D0%B3?%D0%BC%D1%96%D1%81%D1%82%D0%BE=%D0%9B%D1%83%D1%86%D1%8C%D0%BA&path=%2Funchanged&flag=a+b')
  self.assertEqual(urlsplit(actual).netloc,urlsplit(original).netloc)
  self.assertEqual(unquote(urlsplit(actual).path),unquote(urlsplit(original).path))
  self.assertEqual(unquote(urlsplit(actual).query),unquote(urlsplit(original).query))
 def test_ascii_source_urls_are_byte_identical(self):
  for url in ['https://example.org/','https://example.org/a%20b?queue=1.1&house=2%2F3','https://example.org:443/api?v=x+y']:
   self.assertEqual(m.request_url(url),url)
 def test_origin_credentials_fragment_and_control_boundaries_fail_before_request(self):
  for url in ['http://example.org/x','https://user:secret@example.org/x','https://example.org/x#section','https://приклад.org/x','https:///missing','https://example.org/x\nInjected:yes']:
   with self.subTest(url=url),patch.object(m.urllib.request,'urlopen') as open_source:
    with self.assertRaises(ValueError):m.fetch(url)
    open_source.assert_not_called()
 def test_fetch_reaches_http_layer_with_ascii_wire_url_and_does_not_make_coverage(self):
  class Response:
   status=200
   def __enter__(self):return self
   def __exit__(self,*args):pass
   def read(self,limit):return b'<html>source page</html>'
   def geturl(self):return m.request_url('https://example.org/графіки/')
  def opened(request,timeout):
   self.assertEqual(timeout,20);request.full_url.encode('ascii')
   self.assertEqual(request.full_url,'https://example.org/%D0%B3%D1%80%D0%B0%D1%84%D1%96%D0%BA%D0%B8/')
   return Response()
  with patch.object(m.urllib.request,'urlopen',side_effect=opened):
   result=m.probe({'id':'synthetic','sourceUrl':'https://example.org/графіки/'},{})
  self.assertEqual(result['status'],'page_available');self.assertEqual(result['httpStatus'],200)
  self.assertEqual(result['leads'],[]);self.assertNotIn('queue',result)
if __name__=='__main__':unittest.main()
