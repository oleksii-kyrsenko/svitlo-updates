import importlib.util,sys,types,unittest
from pathlib import Path
sys.modules.setdefault('playwright',types.ModuleType('playwright'));fake=types.ModuleType('playwright.sync_api');fake.sync_playwright=None;sys.modules.setdefault('playwright.sync_api',fake)
s=importlib.util.spec_from_file_location('app',Path(__file__).resolve().parents[1]/'browser-zap-app.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Projection(unittest.TestCase):
 def test_long_explicit_house_list_is_not_treated_as_personal_identifier(self):
  houses='|'.join(str(i)+'А' for i in range(1,35));rows,_,q=m.project([['вул. Нова',houses,'1.2','',9]]);self.assertEqual(rows[0][1],houses);self.assertFalse(q)
  self.assertFalse(m.structured_house_list('1234567890123'));self.assertFalse(m.structured_house_list('ім’я власника та довгий опис'))
 def test_frontend_schema_must_keep_gpv_and_gav_separate_and_no_city_heading_carry(self):
  code={'loadData':'getData()','loadHouses':'row[0] === street row[1]','showQueue':'row[0] === street && row[1] === house; gpvQueue = row[2]; zova = row[3]; gavQueue = row[4]','filterStreets':'row[0]'};m.verify_frontend(code)
  with self.assertRaises(ValueError):m.verify_frontend({**code,'showQueue':code['showQueue'].replace('gpvQueue = row[2]','gpvQueue = row[4]')})
 def test_reviewed_authority_requires_original_hash_active_link_and_unexpired_original_time(self):
  url='https://script.google.com/macros/s/public/exec';raw=('<a href="'+url+'">Дізнатися свою чергу по м. Запоріжжя</a>').encode();meta={'sourceUrl':m.INDEX,'checkedAt':1000,'expiresAt':86401000,'sha256':m.sha(raw)}
  self.assertEqual(m.authority_snapshot(raw,meta,url,2000)['url'],url)
  for change in [{'checkedAt':3000},{'expiresAt':3000},{'sha256':'0'*64}]:
   with self.assertRaises(ValueError):m.authority_snapshot(raw,{**meta,**change},url,2000)
  for invalid in [b'link removed',b'<!--'+raw+b'-->']:
   with self.assertRaises(ValueError):m.authority_snapshot(invalid,{**meta,'sha256':m.sha(invalid)},url,2000)
 def test_gpvisfixedcolumn_exemptionsveto_and_gav_never_substitutes(self):
  rows,_,_=m.project([['вул. Нова','2','1.2','',9],['вул. Нова','4','','частина будинку',8]])
  self.assertEqual(rows,[['вул. Нова','2','1.2',False],['вул. Нова','4','',True]])
 def test_unexpected_long_account_like_address_is_not_persisted(self):
  rows,_,q=m.project([['вул. Нова','1234567890123','1.2','',9]]);self.assertFalse(rows);self.assertEqual(q[0]['fieldIssues'][0]['field'],'house');self.assertNotIn('1234567890123',str(q))
  self.assertEqual(q[0]['sourceStreetSha256'],m.source_street_hash('вулиця Нова'));self.assertNotIn('вул. Нова',str(q))
 def test_unknown_street_cannot_produce_a_fake_binding(self):
  rows,_,q=m.project([['street1234567890123','2','1.2','',9]]);self.assertFalse(rows);self.assertIsNone(q[0]['sourceStreetSha256'])
 def test_exemption_text_extra_columns_and_gav_are_not_persisted(self):
  rows,_,_=m.project([['вул. Нова','2','1.2','private exemption text',9,'private extra']]);self.assertEqual(rows,[['вул. Нова','2','1.2',True]])
 def test_unsafe_queue_field_keeps_safe_address_only_as_unknown(self):
  rows,_,q=m.project([['вул. Нова','2','account1234567890123','',9]]);self.assertEqual(rows,[['вул. Нова','2',None,False]]);self.assertNotIn('1234567890123',str(q))
 def test_no_arbitrary_sources_or_accounts(self):
  self.assertTrue(m.allowed('https://script.google.com/macros/s/public/exec'));self.assertFalse(m.allowed('https://accounts.google.com/ServiceLogin'));self.assertFalse(m.allowed('http://script.google.com/'));self.assertFalse(m.allowed('https://attacker.example/'))
 def test_official_parent_redirect_cannot_be_attributed_to_original_operator_page(self):
  m.official_parent_response(m.INDEX)
  for url in ['https://attacker.example/outage/','http://www.zoe.com.ua/outage/','https://www.zoe.com.ua/new-source/','https://www.zoe.com.ua@attacker.example/outage/']:
   with self.assertRaisesRegex(ValueError,'redirected_review_required'):m.official_parent_response(url)
 def test_ordinary_parent_preserves_response_status_original_bytes_and_real_clock(self):
  class Response:
   status=403
   def __enter__(self):return self
   def __exit__(self,*args):pass
   def geturl(self):return m.INDEX
   def read(self,limit):self.limit=limit;return b'access denied'
  original=Response()
  def opener(request,timeout):
   self.assertEqual(request.full_url,m.INDEX);self.assertEqual(timeout,15);return original
  response=m.ordinary_parent(opener=opener,clock=lambda:1234)
  self.assertEqual((response.status,response.body(),response.checkedAt),(403,b'access denied',1234));self.assertEqual(original.limit,2000001)
 def test_ordinary_parent_rejects_oversize_source_and_an_unreviewed_redirect(self):
  class Response:
   status=200
   def __enter__(self):return self
   def __exit__(self,*args):pass
   def geturl(self):return m.INDEX
   def read(self,limit):return b'x'*2000001
  with self.assertRaisesRegex(ValueError,'too_large'):m.ordinary_parent(opener=lambda *a,**k:Response())
  Response.geturl=lambda self:'https://attacker.example/'
  with self.assertRaisesRegex(ValueError,'redirected_review_required'):m.ordinary_parent(opener=lambda *a,**k:Response())
 def test_only_real_timeout_is_a_temporary_alternative_transport_failure(self):
  self.assertTrue(m.temporary_timeout(TimeoutError()))
  self.assertTrue(m.temporary_timeout(m.urllib.error.URLError(TimeoutError())))
  self.assertFalse(m.temporary_timeout(m.urllib.error.URLError('certificate verification failed')))
  self.assertFalse(m.temporary_timeout(ValueError('source changed')))
if __name__=='__main__':unittest.main()
