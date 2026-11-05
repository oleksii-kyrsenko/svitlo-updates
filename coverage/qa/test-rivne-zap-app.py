import importlib.util,sys,unittest,tempfile,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));s=importlib.util.spec_from_file_location('app',Path(__file__).resolve().parents[1]/'collect-rivne-zap-app.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
G={'settlement':'Запоріжжя','community':'Запорізька міська громада'}
def packet(rows,quarantine=[]):return {'rows':rows,'quarantinedRows':quarantine,'checkedAt':1000,'expiresAt':10000,'sourceUrl':'https://script.google.com/macros/s/public/exec'}
def decode(rows,q=[]):return m.decode(packet(rows,q),G)
class WholeHouseConsensus(unittest.TestCase):
 def test_literal_only_source_time_and_city_scope(self):
  rows,obs,_=decode([['вул. Нова','2-А','1.2',False]])
  self.assertEqual(rows[0]['houses'],['2-А']);self.assertEqual(rows[0]['checkedAt'],1000);self.assertEqual(rows[0]['expiresAt'],10000);self.assertEqual(rows[0]['settlement'],'Запоріжжя');self.assertEqual(obs[0]['house'],'2-А')
 def test_unknown_GPV_connection_vetoes_a_positive_for_same_exact_house(self):
  rows,obs,r=decode([['вул. Нова','2','1.2',False],['вулиця Нова','2','',False]])
  self.assertFalse(rows);self.assertEqual(len(obs),1);self.assertEqual(r['abstentions'][0]['reason'],'unknown_GPV_connection')
 def test_ZOVA_exemption_vetoes_even_when_GPV_agrees(self):
  rows,_,r=decode([['вул. Нова','2','1.2',False],['вул. Нова','2','1.2',True]])
  self.assertFalse(rows);self.assertEqual(r['abstentions'][0]['reason'],'explicit_ZOVA_partial_exemption')
 def test_conflicting_connections_are_not_first_queue_wins(self):
  rows,_,_=decode([['вул. Нова','2','1.2',False],['вул. Нова','2','2.1',False]])
  self.assertFalse(rows)
 def test_Cyrillic_Latin_suffixes_share_same_conflict_identity(self):
  rows,obs,_=decode([['вул. Нова','2-А','1.2',False],['вул. Нова','2A','2.1',False]])
  self.assertFalse(rows);self.assertEqual(len(obs),1)
 def test_pipe_never_generates_house_or_fraction_and_unknown_pipe_vetoes_literal(self):
  rows,obs,_=decode([['вул. Нова','1|3','1.2',False]])
  self.assertFalse(rows);self.assertFalse(obs)
  rows,obs,_=decode([['вул. Нова','1|3','',False],['вул. Нова','1/3','1.2',False]])
  self.assertFalse(rows);self.assertEqual(obs[0]['house'],'1/3')
 def test_unqualified_range_never_expands_and_vetoes_conflicting_literal(self):
  rows,obs,_=decode([['вул. Нова','1-9','2.1',False],['вул. Нова','4','1.2',False]])
  self.assertFalse(rows);self.assertEqual({o['house'] for o in obs},{'4'})
 def test_partial_entrance_unknown_connection_cannot_be_ignored(self):
  rows,_,_=decode([['вул. Нова','10','1.2',False],['вул. Нова','10 п.1–2','',False]])
  self.assertFalse(rows)
 def test_same_queue_uncertain_encoding_does_not_create_new_positive(self):
  rows,obs,_=decode([['вул. Нова','1','1.2',False],['вул. Нова','1|3','1.2',False]])
  self.assertEqual([r['houses'] for r in rows],[['1']]);self.assertEqual([o['house'] for o in obs],['1'])
 def test_quarantine_road_hash_blocks_known_literal_without_creating_an_address(self):
  q=[{'sourceStreetSha256':m.source_street_hash('вул.Нова'),'fieldIssues':[{'field':'house'}]}];rows,obs,_=decode([['вул. Нова','2','1.2',False]],q)
  self.assertFalse(rows);self.assertEqual([o['house'] for o in obs],['2'])
 def test_unbound_quarantined_address_cannot_establish_whole_house_consensus(self):
  for field in ['street','house']:
   with self.assertRaisesRegex(ValueError,'unbound_quarantined_address_connection'):
    decode([['вул. Нова','2','1.2',False]],[{'fieldIssues':[{'field':field}]}])
 def test_quarantined_GPV_keeps_the_safe_address_as_an_unknown_connection(self):
  rows,obs,r=decode([['вул. Нова','2','1.2',False],['вул. Нова','2',None,False]],[{'fieldIssues':[{'field':'gpv'}]}])
  self.assertFalse(rows);self.assertEqual(len(obs),1);self.assertEqual(r['abstentions'][0]['reason'],'unknown_GPV_connection')
 def test_locality_landmark_untyped_and_ambiguous_type_rows_never_default_to_city(self):
  rows,obs,r=decode([['Балабіне','Депутатська73','1.2',False],['с. Високогірне вул. Мічуріна','1в','1.2',False],['вул. Нова (с. Інше)','2','1.2',False],['СТ Приклад','2','1.2',False],['пр. Невизначений','2','1.2',False]])
  self.assertFalse(rows);self.assertFalse(obs);self.assertEqual(len(r['declinedRows']),5)
 def test_gav_is_not_an_input_column_and_extra_columns_fail(self):
  with self.assertRaises(ValueError):decode([['вул. Нова','2','','',9]])
 def test_quarantine_hash_protocol_matches_capture(self):
  self.assertEqual(m.source_street_hash('вул.Нова (Стара)'),m.source_street_hash('вулиця Нова'))
 def evidence(self,folder):
  url='https://script.google.com/macros/s/public/exec';label='Дізнатися свою чергу по м. Запоріжжя';raw=('<a href="'+url+'">'+label+'</a>').encode();(folder/'reviewed-authority-original.html').write_bytes(raw)
  code={'loadData':'streetData=data; getData()','loadHouses':'row[0] === street; row[1]','showQueue':'row[0] === street && row[1] === house;gpvQueue=row[2];zova=row[3];gavQueue=row[4]'};front=json.dumps(code).encode();(folder/'official-public-frontend-functions.json').write_bytes(front)
  p={'schemaVersion':1,'operatorId':'zaporizhzhia','regionId':'UA-23','settlement':'Запоріжжя','sourceUrl':url,'checkedAt':2000,'expiresAt':86401000,'authority':{'sourceUrl':m.PARENT,'checkedAt':1000,'expiresAt':86401000,'sha256':m.sha(raw),'method':'previously-reviewed'},'officialCityScopeLabel':label,'frontendSchema':{'sourceUrl':url,'sha256':m.sha(front),'GPVcolumn':2,'partialExemptionsColumn':3,'GAVcolumnNeverSubstituted':4}};return p
 def test_authority_original_age_hash_and_exact_active_city_resource_are_required(self):
  with tempfile.TemporaryDirectory() as d:
   f=Path(d);p=self.evidence(f);m.verify_projection(p,f/'projection.json',3000)
   with self.assertRaises(ValueError):m.verify_projection(p,f/'projection.json',86401001)
   (f/'reviewed-authority-original.html').write_bytes(b'changed source')
   with self.assertRaises(ValueError):m.verify_projection(p,f/'projection.json',3000)
   p=self.evidence(f);raw=(f/'reviewed-authority-original.html').read_bytes();raw=b'<!--'+raw+b'-->';(f/'reviewed-authority-original.html').write_bytes(raw);p['authority']['sha256']=m.sha(raw)
   with self.assertRaises(ValueError):m.verify_projection(p,f/'projection.json',3000)
 def test_observed_frontend_cannot_swap_GPV_with_GAV(self):
  with tempfile.TemporaryDirectory() as d:
   f=Path(d);p=self.evidence(f);front=(f/'official-public-frontend-functions.json').read_bytes().replace(b'gpvQueue=row[2]',b'gpvQueue=row[4]');(f/'official-public-frontend-functions.json').write_bytes(front);p['frontendSchema']['sha256']=m.sha(front)
   with self.assertRaises(ValueError):m.verify_projection(p,f/'projection.json',3000)
if __name__=='__main__':unittest.main()
