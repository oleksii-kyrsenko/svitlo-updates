import importlib.util,sys,types,unittest
from pathlib import Path
sys.modules.setdefault('playwright',types.ModuleType('playwright'));fake=types.ModuleType('playwright.sync_api');fake.sync_playwright=None;sys.modules.setdefault('playwright.sync_api',fake)
s=importlib.util.spec_from_file_location('app',Path(__file__).with_name('rivne-zap-public-app.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Projection(unittest.TestCase):
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
 def test_exemption_text_extra_columns_and_gav_are_not_persisted(self):
  rows,_,_=m.project([['вул. Нова','2','1.2','private exemption text',9,'private extra']]);self.assertEqual(rows,[['вул. Нова','2','1.2',True]])
 def test_unsafe_queue_field_keeps_safe_address_only_as_unknown(self):
  rows,_,q=m.project([['вул. Нова','2','account1234567890123','',9]]);self.assertEqual(rows,[['вул. Нова','2',None,False]]);self.assertNotIn('1234567890123',str(q))
 def test_no_arbitrary_sources_or_accounts(self):
  self.assertTrue(m.allowed('https://script.google.com/macros/s/public/exec'));self.assertFalse(m.allowed('https://accounts.google.com/ServiceLogin'));self.assertFalse(m.allowed('http://script.google.com/'));self.assertFalse(m.allowed('https://attacker.example/'))
if __name__=='__main__':unittest.main()
