import importlib.util,sys,types,unittest
from pathlib import Path
sys.modules.setdefault('playwright',types.ModuleType('playwright'));fake=types.ModuleType('playwright.sync_api');fake.sync_playwright=None;sys.modules.setdefault('playwright.sync_api',fake)
s=importlib.util.spec_from_file_location('app',Path(__file__).with_name('rivne-zap-public-app.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Projection(unittest.TestCase):
 def test_gpvisfixedcolumn_exemptionsveto_and_gav_never_substitutes(self):
  rows,_=m.project([['вул. Нова','2','1.2','',9],['вул. Нова','4','','частина будинку',8]])
  self.assertEqual(rows,[['вул. Нова','2','1.2',False],['вул. Нова','4','',True]])
 def test_unexpected_long_account_like_address_is_not_persisted(self):
  with self.assertRaises(ValueError):m.project([['вул. Нова','1234567890123','1.2','',9]])
 def test_exemption_text_extra_columns_and_gav_are_not_persisted(self):
  rows,_=m.project([['вул. Нова','2','1.2','private exemption text',9,'private extra']]);self.assertEqual(rows,[['вул. Нова','2','1.2',True]])
 def test_no_arbitrary_sources_or_accounts(self):
  self.assertTrue(m.allowed('https://script.google.com/macros/s/public/exec'));self.assertFalse(m.allowed('https://accounts.google.com/ServiceLogin'));self.assertFalse(m.allowed('http://script.google.com/'));self.assertFalse(m.allowed('https://attacker.example/'))
if __name__=='__main__':unittest.main()
