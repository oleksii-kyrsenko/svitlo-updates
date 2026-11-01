import sys,unittest,importlib.util,tempfile,json,contextlib,io
from unittest.mock import patch
from types import SimpleNamespace
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from source_utils import record

def module(name):
 spec=importlib.util.spec_from_file_location(name,Path(__file__).resolve().parents[1]/(name+'.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
class BatchControls(unittest.TestCase):
 def test_special_dtek_schedule_paths_match_official_directory(self):
  m=module('collect-batch-c')
  for op in ('dtek-pem','dtek-vvm'):self.assertEqual(m.dtek_page_url(op),'https://'+m.DTEK[op]+'/ua/shutdowns-schedule')
  self.assertEqual(m.dtek_page_url('dtek-odesa'),'https://www.dtek-oem.com.ua/ua/shutdowns')
 def test_street_type_spacing_is_normalised_without_changing_its_identity(self):
  r=record('test','UA-46','Зразок','Зразкова','ПРОВ.Нова','1','8','https://example.org',1000)
  self.assertEqual(r['street'],'ПРОВ. Нова');self.assertEqual(r['houses'],['1'])
 def test_zero_and_unrecognised_queue_cannot_be_published(self):
  for q in ['0','0.0','невідомо','Інший ОСР']:
   self.assertIsNone(record('test','UA-46','Зразок','Зразкова','Нова','1',q,'https://example.org',1000))
 def test_official_html_city_and_literal_house_are_kept(self):
  m=module('batch-a');rows=m.parse_chernivtsi('<title>Зразок / Пошук групи</title><div><p>Нова</p><b>буд. 1-А</b><u>8</u></div>',1)
  self.assertEqual(rows[0]['settlement'],'Зразок');self.assertEqual(rows[0]['house'],'1-А');self.assertEqual(rows[0]['queue'],'8')
 def test_different_connections_never_choose_first_queue(self):
  m=module('collect-batch-b');self.assertIsNone(m.consensus(['1.1','2.1']));self.assertIsNone(m.consensus(['1.1','0']));self.assertEqual(m.consensus(['1.1','1.1']),'1.1')
 def test_dtek_data_parser_rejects_javascript(self):
  m=module('collect-batch-c');self.assertEqual(m.assignment('DisconSchedule.streets = {"Зразок":["Нова"]};','DisconSchedule.streets'),{'Зразок':['Нова']})
  with self.assertRaises(ValueError):m.assignment('DisconSchedule.streets = evil();','DisconSchedule.streets')
 def test_collection_clock_does_not_expire_fresh_records_before_publication(self):
  m=module('collect-batch-c')
  r=record('dtek-kyiv','UA-30','Зразок','Зразкова','Нова','1','1.1','https://example.org/source',1001000)
  with tempfile.TemporaryDirectory() as folder:
   output=str(Path(folder)/'packet.json')
   with patch.object(sys,'argv',['collector','--operator','dtek-kyiv','--output',output]),patch.object(m,'Client',return_value=SimpleNamespace(requests=1,observations=[])),patch.object(m,'yasno',return_value=([r],[],[],1)),patch.object(m.time,'time',side_effect=[1000,1002]),contextlib.redirect_stdout(io.StringIO()):m.main()
   packet=json.loads(Path(output).read_text())
   self.assertGreaterEqual(packet['generatedAt'],r['checkedAt']);self.assertEqual(packet['expiresAt'],r['expiresAt'])

if __name__=='__main__':unittest.main()
