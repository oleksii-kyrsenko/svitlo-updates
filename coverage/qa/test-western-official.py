import gzip,importlib.util,io,pathlib,sys,unittest
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
s=importlib.util.spec_from_file_location('western',pathlib.Path(__file__).resolve().parents[1]/'collect-western-official.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
NOW=1793730000000
DOC={'queue':'1.1','url':'https://oe.if.ua/uploads/question_document/document/69ccca051814b5166d9d3a89/1.1.pdf','effectiveUntil':1806537600000}
G={'regionId':'UA-26','settlement':'Івано-Франківськ','community':'Івано-Франківська міська громада'}
def index():
 links=''.join(f'<a href="/uploads/question_document/document/69ccca051814b5166d9d3a89/{a}.{b}.pdf"><div class="name">{a}.{b}</div></a>' for a in range(1,7) for b in (1,2))
 return '<h3>Графіки аварійних вимкнень</h3><p>2026</p><ul><a href="wrong.pdf">1 черга</a></ul><h3>Графіки погодинних вимкнень</h3><p>Графіки погодинних вимкнень з 01.10.2026 до 01.04.2027</p><ul>'+links+'</ul>'
def claim(numbers,queue='1.1',street='Навчальна'):
 return m.parse_tables([[['1',queue.split('.')[1],'Івано-Франківський',G['settlement'],street,numbers]]],{**DOC,'queue':queue},G['settlement'])[0]
class WesternOfficial(unittest.TestCase):
 def test_current_all_twelve_GPV_links_ignore_GAV_and_comments(self):
  docs=m.documents(index(),NOW);self.assertEqual(len(docs),12);self.assertEqual({d['queue'] for d in docs},{f'{a}.{b}' for a in range(1,7) for b in (1,2)})
  self.assertEqual(len(m.documents('<!--'+index()+'-->'+index(),NOW)),12)
 def test_missing_duplicate_and_untrusted_current_document_fail_closed(self):
  for text in (index().replace('<div class="name">6.2</div>',''),index().replace('</ul>','<a href="/uploads/question_document/document/69ccca051814b5166d9d3a89/1.1.pdf"><div class="name">1.1</div></a></ul>'),index().replace('/uploads/','https://other.example/uploads/')):
   with self.assertRaises(ValueError):m.documents(text,NOW)
 def test_expired_future_or_missing_period_not_renewed(self):
  for now in (m.utc('30.09.2026'),m.utc('01.04.2027')):
   with self.assertRaises(ValueError):m.documents(index(),now)
  with self.assertRaises(ValueError):m.documents(index().replace('01.10.2026','недатовано'),NOW)
 def test_raw_gzip_is_normally_decoded_and_bounded(self):
  self.assertEqual(m.decoded(gzip.compress(index().encode())),index().encode())
  with patch.object(m,'MAX',3):
   with self.assertRaises(ValueError):m.decoded(gzip.compress(b'1234'))
 def test_exact_city_column_excludes_same_district_and_other_localities(self):
  rows=[['1','1','Івано-Франківський','Бабухів','Навчальна','7'],['1','1','Івано-Франківський','Івано-Франківськ','Навчальна','9']]
  result=m.parse_tables([rows],DOC,G['settlement']);self.assertEqual(result[0]['houses'],['9']);self.assertEqual(len(result),1)
 def test_document_and_city_queue_identity_must_agree(self):
  rows=[[['1','2','Івано-Франківський','Івано-Франківськ','Навчальна','9']]]
  with self.assertRaises(ValueError):m.parse_tables(rows,DOC,G['settlement'])
  rows=[[['1','1','Калуський','Івано-Франківськ','Навчальна','9']]]
  with self.assertRaises(ValueError):m.parse_tables(rows,DOC,G['settlement'])
 def test_real_official_1_1_house_excerpt_preserves_suffixes(self):
  # Current source1.1 PDF city table, Барнича4 and Бистриця6а/46/47/52/59/65/73.
  rows=[[['1','1','Івано-Франківський','Івано-Франківськ','Барнича','4'],['1','1','Івано-Франківський','Івано-Франківськ','Бистриця','6а, 46, 47, 52, 59, 65, 73']]]
  r=m.parse_tables(rows,DOC,G['settlement']);self.assertEqual(r[1]['houses'],['6а','46','47','52','59','65','73']);self.assertEqual(r[0]['street'],'Барнича')
 def test_ranges_never_expand_and_conflicting_range_vetoes_literal(self):
  a=claim('1-9, 12-А');b=claim('3, 14','1.2')
  rows,obs,n=m.consolidate([a,b],G,NOW,NOW+10000)
  self.assertEqual({h for r in rows for h in r['houses']},{'12-А','14'});self.assertEqual({o['house'] for o in obs},{'12-А','3','14'});self.assertEqual(n,1)
 def test_partial_apartment_or_multiple_connections_cannot_assign_house(self):
  rows,obs,n=m.consolidate([claim('9 кв.2, 12'),claim('9, 12','1.2')],G,NOW,NOW+10000)
  self.assertFalse(rows);self.assertEqual(len(obs),2);self.assertEqual(n,2)
 def test_reverse_numeric_token_is_ambiguous_not_expanded_or_reinterpreted(self):
  c=claim('400-2, 18');self.assertEqual(c['houses'],['18']);self.assertEqual(c['unknownHouses'],['400']);self.assertFalse(c['ranges'])
  rows,_,_=m.consolidate([c,claim('400','1.2')],G,NOW,NOW+10000);self.assertEqual([h for r in rows for h in r['houses']],['18'])
 def test_suffixes_canonicalize_without_collapsing_literal_different_houses(self):
  rows,obs,n=m.consolidate([claim('9-А, 9/1-А, 11'),claim('9А','1.2')],G,NOW,NOW+10000)
  self.assertEqual({h for r in rows for h in r['houses']},{'9/1-А','11'});self.assertEqual(n,1)
 def test_large_street_chunks_stay_bounded_and_original_times_unchanged(self):
  c=claim(', '.join(str(i) for i in range(1,132)));rows,obs,n=m.consolidate([c],G,NOW,NOW+1234)
  self.assertEqual(len(rows),3);self.assertEqual(sum(len(r['houses']) for r in rows),131);self.assertTrue(all(len(r['houses'])<=60 and len(r['quote'])<2500 and r['checkedAt']==NOW and r['expiresAt']==NOW+1234 for r in rows))
 def test_lane_and_street_names_preserve_source_type(self):
  rows,_,_=m.consolidate([claim('9',street='пров. Навчальний'),claim('9','1.2',street='Навчальний')],G,NOW,NOW+10000)
  self.assertEqual({r['street'] for r in rows},{'пров. Навчальний','Навчальний'})
if __name__=='__main__':unittest.main()
