import importlib.util,unittest
spec=importlib.util.spec_from_file_location('remainder','coverage/collect-remainder.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class RemainderTests(unittest.TestCase):
 def test_complete_localities_only(self):
  tables=[[['Зразкова','с.Перший (повністю), с.Другий (частково), с.Третій (повністю)','вул.Нова','1.2']]]
  rows=m.rivne_records(tables,'https://example.org/source.pdf',1000)
  self.assertEqual([r['settlement'] for r in rows],['Перший','Третій']);self.assertTrue(all(r['scope']=='settlement' for r in rows));self.assertEqual(rows[0]['community'],'Зразкова')
 def test_partial_conflict_blocks_whole_locality(self):
  rows=m.rivne_records([[['Зразкова','с.Перший (повністю)','','1.2'],['Зразкова','с.Перший (частково)','','2.2']]],'https://example.org',1000)
  self.assertEqual(rows,[])
 def test_unknown_queue_or_community(self):
  self.assertEqual(m.rivne_records([[['','с.Перший (повністю)','','1.2']]],'https://example.org',1000),[])
  self.assertEqual(m.rivne_records([[['Зразкова','с.Перший (повністю)','','інша']]],'https://example.org',1000),[])
 def test_literal_houses_no_ranges_or_landmarks(self):
  source='<div class="title_p">Підчерга 2-І</div><table><tr><td>м.Зразок</td><td>підстанція</td><td>7</td><td>тип</td><td>вул. Нова 7, 9А;<br>вул. Інша 10-20;<br>магазин</td></tr></table>'
  rows=m.atom_house_rows(source,'https://example.org/source',1000,lambda *a:'Зразкова')
  self.assertEqual(len(rows),1);self.assertEqual(rows[0]['houses'],['7','9А']);self.assertEqual(rows[0]['queue'],'2.1')
  self.assertEqual(m.atom_house_rows(source,'https://example.org/source',1000,lambda *a:None),[])
 def test_conflicting_connections_not_chosen(self):
  row='<tr><td>м.Зразок</td><td>станція</td><td>7</td><td>тип</td><td>вул. Нова 7;</td></tr>'
  source='<div class="title_p">Підчерга 2-І</div>'+row+'<div class="title_p">Підчерга 3-ІІ</div>'+row
  self.assertEqual(m.atom_house_rows(source,'https://example.org/source',1000,lambda *a:'Зразкова'),[])
if __name__=='__main__':unittest.main()
