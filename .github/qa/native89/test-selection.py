import importlib.util,pathlib,unittest
spec=importlib.util.spec_from_file_location('selection',pathlib.Path(__file__).with_name('selection.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Selection(unittest.TestCase):
 def test_default_six_native_three_live(self):
  s=m.selection();self.assertTrue(s['runNative'] and s['runLive']);self.assertEqual(s['nativeMatrix'],{'api':[30,35,36],'theme':['aurora','moss']});self.assertEqual(s['liveMatrix'],{'api':[30,35,36]})
 def test_one_failed_native_combination_only(self):
  s=m.selection('native','36','moss');self.assertTrue(s['runNative']);self.assertFalse(s['runLive']);self.assertEqual(s['nativeMatrix'],{'api':[36],'theme':['moss']})
 def test_live_only_retains_all_three_apis(self):
  s=m.selection('live');self.assertFalse(s['runNative']);self.assertTrue(s['runLive']);self.assertEqual(s['liveMatrix'],{'api':[30,35,36]})
 def test_invalid_and_injected_selectors_fail_instead_of_widening(self):
  for args in [('other','all','all'),('native','36;echo bad','moss'),('native','[36]','moss'),('all','all','../moss'),('all','37','all')]:
   with self.subTest(args=args),self.assertRaises(ValueError):m.selection(*args)
if __name__=='__main__':unittest.main()
