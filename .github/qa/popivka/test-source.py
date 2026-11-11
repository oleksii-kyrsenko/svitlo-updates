import importlib.util,datetime,pathlib,unittest
spec=importlib.util.spec_from_file_location('observed_source',pathlib.Path(__file__).with_name('source.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Source(unittest.TestCase):
 today=datetime.date(2026,11,11)
 def fixture(self,fragment='15:00 - 19:00'):
  return ('<h1>Графік погодинних відключень (ГПВ) на 11 листопада</h1><p>10.11.2026 22:10</p><p>Години відсутності електропостачання:</p>'+''.join('<p>'+q+' '+(fragment if q=='6.2' else '07:00 - 10:00')+'</p>' for q in sorted(m.QUEUES))+'<p>Свою чергу</p>').encode()
 def test_independent_dom_reader_joins_adjacent_inline_fragments(self):
  result=m.parse(self.fixture('<span>15:00 - 19:0</span><span>0</span>'),self.today,'https://www.cherkasyoblenergo.com/media/test')
  self.assertEqual(len(result['queues']),12);self.assertEqual(result['queues']['6.2'],[(900,1140)]);self.assertEqual(result['queues']['3.1'],[(420,600)])
 def test_existing_spaces_and_block_boundaries_are_not_guessed(self):
  for fragment in ['15:00 - 19:0 0','15:00 - 19:0<br>0','15:00 - 19:0','15:00 - 29:00','15:00 - 14:00']:
   with self.subTest(fragment=fragment),self.assertRaises(ValueError):m.parse(self.fixture(fragment),self.today,'https://www.cherkasyoblenergo.com/media/test')
 def test_missing_queue_and_wrong_year_cannot_pass(self):
  for raw in [self.fixture().replace(b'<p>6.2 15:00 - 19:00</p>',b''),self.fixture().replace(b'10.11.2026 22:10',b'10.11.2025 22:10')]:
   with self.assertRaises(ValueError):m.parse(raw,self.today,'https://www.cherkasyoblenergo.com/media/test')
 def test_scripts_are_not_duplicate_evidence(self):
  raw=self.fixture()+b'<script>6.2 08:00-09:00</script>';self.assertEqual(len(m.parse(raw,self.today,'https://www.cherkasyoblenergo.com/media/test')['queues']),12)
 def test_partial_requires_update_heading_and_timestamp(self):
  full=self.fixture();raw=full.replace('<h1>Графік'.encode(),'<h1>Оновлено графік'.encode())
  for q in m.QUEUES-{'3.1'}:
   line='<p>'+q+' '+('15:00 - 19:00' if q=='6.2' else '07:00 - 10:00')+'</p>';raw=raw.replace(line.encode(),b'')
  result=m.parse(raw,self.today,'https://www.cherkasyoblenergo.com/media/test');self.assertTrue(result['partial']);self.assertEqual(list(result['queues']),['3.1'])
if __name__=='__main__':unittest.main()
