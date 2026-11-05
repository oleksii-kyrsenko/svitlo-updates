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
if __name__=='__main__':unittest.main()
