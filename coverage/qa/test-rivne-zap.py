import importlib.util,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
spec=importlib.util.spec_from_file_location('rivne_zap',Path(__file__).resolve().parents[1]/'collect-rivne-zap.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
G={'settlement':'Рівне','community':'Рівненська міська громада'}
URL='https://www.roe.vsei.ua/wp-content/uploads/2026/10/GPV_cherga_misto_Rivne-1.pdf'
def tables(*rows):return [[['№ п/п','Назви вулиць та номери будинків в м.Рівне','підчерга'],*[[str(i),'',f'{a},{b}'] for i,(a,b) in enumerate(( (a,b) for a in range(1,7) for b in (1,2)))],*[[str(i),text,q] for i,(text,q) in enumerate(rows)]]]
class CurrentCity(unittest.TestCase):
 def test_active_official_city_attachment_ignores_comment_and_other_document(self):
  link=f'<a href="{URL}">Дізнатися чергу відключень у м. Рівне</a>'
  self.assertEqual(m.city_link('<!--'+link.replace('Rivne-1','Rivne-2')+'-->'+link),URL)
  for body in ['<!--'+link+'-->',link+link.replace('Rivne-1','Rivne-2'),link.replace('www.roe.vsei.ua','elsewhere.example')]:
   with self.assertRaises(ValueError):m.city_link(body)
 def test_punctuation_spacing_never_changes_road_names_or_types(self):
  self.assertEqual(m.canonical_street('вул.Соборна'),'вул. Соборна');self.assertEqual(m.canonical_street('пров.Робітничий'),'пров. Робітничий')
  self.assertEqual(m.canonical_street('Вулкана'),'Вулкана');self.assertEqual(m.canonical_street('вул. 16 Липня'),'вул. 16 Липня')
 def test_actual_current_pdf_literal_excerpt_keeps_original_quote_and_suffixes(self):
  excerpt='вул.Кулика і Гудачека 44, 46, 52, 54, 56, 58, вул.Млинівська 30, 34, 38, 41, 41а'
  rows,obs,_=m.decode_tables(tables((excerpt,'1,1')),URL,1000,G)
  self.assertEqual(rows[0]['street'],'вул. Кулика і Гудачека');self.assertEqual(rows[0]['houses'],['44','46','52','54','56','58'])
  self.assertIn('41а',rows[1]['houses']);self.assertIn(excerpt,rows[0]['quote']);self.assertTrue(all(o['checkedAt']==1000 and o['expiresAt']==86401000 for o in obs))
 def test_missing_queue_or_wrong_city_header_never_releases_partial_packet(self):
  t=tables(('вул.Нова 2','1,1'));t[0]=[r for r in t[0] if r[2]!='6,2']
  with self.assertRaises(ValueError):m.decode_tables(t,URL,1000,G)
  t=tables(('вул.Нова 2','1,1'));t[0][0][1]='Назви вулиць та номери будинків в м.Інше'
  with self.assertRaises(ValueError):m.decode_tables(t,URL,1000,G)
 def test_qualified_parity_does_not_veto_opposite_parity(self):
  rows,_,_=m.decode_tables(tables(('вул.Нова 2-8 (парні)','1,1'),('вул.Нова 3, 5','2,1')),URL,1000,G)
  self.assertEqual({r['queue']:r['houses'] for r in rows},{'1.1':['2','4','6','8'],'2.1':['3','5']})
 def test_unqualified_ranges_veto_conflicting_literal_and_keep_negative_observation(self):
  rows,obs,_=m.decode_tables(tables(('вул.Нова 1-9','1,1'),('вул.Нова 3, 11','2,1')),URL,1000,G)
  self.assertEqual([r['houses'] for r in rows],[['11']]);self.assertEqual({o['house'] for o in obs},{'3','11'})
 def test_conflicting_literals_cannot_become_first_queue_wins(self):
  rows,obs,_=m.decode_tables(tables(('вул.Нова 2, 4','1,1'),('вул. Нова 2, 6','2,1')),URL,1000,G)
  self.assertEqual({r['queue']:r['houses'] for r in rows},{'1.1':['4'],'2.1':['6']});self.assertIn('2',{o['house'] for o in obs})
 def test_bare_partial_and_business_descriptions_never_become_whole_street(self):
  rows,_,_=m.decode_tables(tables(('вул.Нова, вул.Друга (частково), ТОВ Приклад 9','1,1')),URL,1000,G)
  self.assertFalse(rows)
 def test_repeated_road_in_one_pdf_row_keeps_all_literal_houses_under_one_id(self):
  rows,_,_=m.decode_tables(tables(('вул.Нова 2, 4, вул.Друга 6, вул.Нова 8','1,1')),URL,1000,G)
  self.assertEqual(len({r['id'] for r in rows}),len(rows));self.assertEqual(next(r['houses'] for r in rows if r['street']=='вул. Нова'),['2','4','8'])
if __name__=='__main__':unittest.main()
