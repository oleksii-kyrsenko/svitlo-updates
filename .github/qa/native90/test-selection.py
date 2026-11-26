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
class HistoricalSelection(unittest.TestCase):
 def test_historical_case_does_not_start_native_fixture_or_live_schedule_jobs(self):
  value=m.selection('historical','35','all');self.assertFalse(value['runNative']);self.assertFalse(value['runLive']);self.assertTrue(value['runHistorical']);self.assertEqual(value['historicalMatrix'],{'api':[35]})
class StreetSelection(unittest.TestCase):
 def test_separate_three_original_cases_never_widen_all_suite(self):
  spec=importlib.util.spec_from_file_location('controls',pathlib.Path(__file__).with_name('street-controls.py'));controls=importlib.util.module_from_spec(spec);spec.loader.exec_module(controls)
  value=m.selection('street');self.assertTrue(value['runStreet']);self.assertFalse(value['runNative'] or value['runLive'] or value['runHistorical']);self.assertEqual(value['streetMatrix']['include'],controls.CASES)
  ordinary=m.selection();self.assertFalse(ordinary['runStreet']);self.assertTrue(ordinary['runHistorical']);self.assertEqual(len(ordinary['nativeMatrix']['api'])*len(ordinary['nativeMatrix']['theme'])+len(ordinary['liveMatrix']['api'])+len(ordinary['historicalMatrix']['api']),12)
 def test_failed_api_rerun_keeps_its_original_case_not_a_cartesian_product(self):
  for api,case in [('30','UA-46-capital-2'),('35','UA-61-capital-1'),('36','UA-21-capital-1')]:
   with self.subTest(api=api):self.assertEqual(m.selection('street',api)['streetMatrix'],{'include':[{'api':int(api),'caseId':case}]})

if __name__=='__main__':unittest.main()
