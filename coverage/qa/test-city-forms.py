import importlib.util,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
spec=importlib.util.spec_from_file_location('cityforms',Path(__file__).resolve().parents[1]/'collect-city-forms.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
GEO={'regionId':'UA-35','settlement':'Навчальне','community':'Навчальна міська громада'}
class KirovHTTP:
 def __init__(self):self.paths=[]
 def text(self,url):return '<select id="fn_office"><option value="3">Навчальна</option><option value="99">Інша</option></select><script>ajaxToken:"volatile"</script>'
 def json(self,url,fields,**options):
  self.paths.append(url.split('?')[0]);assert fields=={'ajax':1,'token':'volatile'};assert options['ajax'] is True
  if '/city/' in url:return {'success':True,'data':[{'CityId':'7','CityName':'Навчальне'}]}
  if '/street/' in url:return {'success':True,'data':[{'StreetId':'8','StreetName':'вул. Нова'}]}
  return {'success':True,'data':[{'CityId':'7','StreetId':'8','HouseName':'2-А','chergGpv':'1.2'},{'CityId':'7','StreetId':'8','HouseName':'2-А','chergGpv':'2.1'},{'CityId':'7','StreetId':'8','HouseName':'4','chergGpv':'3.1'}]}
class Controls(unittest.TestCase):
 def test_all_connections_must_agree_and_unknown_is_not_ignored(self):
  self.assertEqual(m.consensus_rows([{'h':'1','q':'1.1'},{'h':'1','q':''},{'h':'2','q':'2.1'}],'h','q'),[('1',None),('2','2.1')])
 def test_house_ranges_and_corpora_are_not_collapsed(self):
  self.assertIsNone(m.house('1-9'));self.assertEqual(m.house('1-А'),'1-А');self.assertEqual(m.house('1/2'),'1/2');self.assertNotEqual(m.house_key('1/2'),m.house_key('12'));self.assertEqual(m.house_key('1-А'),m.house_key('1A'))
  self.assertEqual(m.consensus_rows([{'h':'1-А','q':'1.1'},{'h':'1A','q':'2.1'}],'h','q'),[('1-А',None)])
 def test_city_dictionary_and_all_house_rows_used_with_sourced_identity(self):
  http=KirovHTTP();state={};rows,observed,completed,errors,meta=m.kirovohrad(http,GEO,state)
  self.assertEqual([r['houses'] for r in rows],[['4']]);self.assertEqual(rows[0]['providerCityId'],'7');self.assertEqual(rows[0]['providerStreetId'],'8');self.assertEqual(len(observed),2);self.assertEqual(completed,['7:8']);self.assertFalse(errors);self.assertEqual(state['crawlStatus'],'complete');self.assertTrue(all('/city/99' not in p for p in http.paths))
 def test_source_cannot_attach_houses_from_another_street(self):
  class Bad(KirovHTTP):
   def json(self,url,*a,**kw):
    result=super().json(url,*a,**kw)
    if '/house/' in url:result['data'][0]['StreetId']='999'
    return result
  rows,observed,completed,errors,meta=m.kirovohrad(Bad(),GEO,{})
  self.assertFalse(rows);self.assertFalse(observed);self.assertFalse(completed);self.assertTrue(errors)
 def test_volyn_uses_gpv_column_exact_city_and_literal_houses_only(self):
  body='<table><tr><th>Район</th><th>Населений пункт</th><th>Вулиця</th><th>Будинок</th><th>ГПВ</th><th>ГАВ</th></tr>'
  body+='<tr><td>Район</td><td>Навчальне</td><td>Нова</td><td>1-А, 3/2</td><td>2.1</td><td>9</td></tr>'
  body+='<tr><td>Район</td><td>Інше</td><td>Нова</td><td>1</td><td>1.1</td><td>9</td></tr>'
  body+='<tr><td>Район</td><td>Навчальне</td><td>Друга</td><td>1-9</td><td>1.1</td><td>9</td></tr></table>'
  rows=m.volyn_rows(body,'Навчальне');literal=[r for r in rows if r['house']];self.assertEqual([r['house'] for r in literal],['1-А','3/2']);self.assertTrue(all(r['queue']=='2.1' for r in literal));self.assertEqual(rows[-1]['_range'],[1,9])
 def test_header_is_required_before_number_extraction(self):
  with self.assertRaisesRegex(ValueError,'header'):m.volyn_rows('<table><tr><td>1.1</td></tr></table>','Навчальне')
 def test_freeform_queue_requires_explicit_single_current_queue(self):
  self.assertEqual(m.prykarpattia_queue({'current':{'hasQueue':'YES','queue':2,'subQueue':1}}),'2.1')
  for current in [{'hasQueue':'MANY','queue':2,'subQueue':1},{'hasQueue':'no','queue':2,'subQueue':1},{'hasQueue':'yes','queue':0,'subQueue':1},{'hasQueue':'yes','queue':2,'subQueue':0}]:self.assertIsNone(m.prykarpattia_queue({'current':current}))
 def test_drupal_state_is_local_to_the_actual_search_form(self):
  body='<form id="other"><input type="hidden" name="form_build_id" value="bad"></form><form id="disconnection-detailed-search-form--2"><input type="hidden" name="form_id" value="source"><input type="hidden" name="form_build_id" value="fresh"></form>'
  fields,_=m.drupal_form(body);self.assertEqual(fields,{'form_id':'source','form_build_id':'fresh'})
  with self.assertRaises(ValueError):m.drupal_form('<form id="other"></form>')
 def test_drupal_answer_ignores_menu_legend_and_schedule_numbers(self):
  self.assertEqual(m.drupal_queue('<div class="disconnection-detailed-table"><p>2.1 черга</p><table><tr><td>6.2 черга</td></tr></table></div>'),'2.1')
  self.assertIsNone(m.drupal_queue('<p>2.1 черга</p><div class="disconnection-detailed-table"><table><td>6.2 черга</td></table></div>'))
  self.assertIsNone(m.drupal_queue('<div class="disconnection-detailed-table"><p>2.1 черга</p><p>4.2 черга</p></div>'))
 def test_autocomplete_ids_come_from_official_labels(self):
  self.assertEqual(m.drupal_autocomplete([{'label':'<span data-id="17">name</span>','value':'м.. Навчальне'}])[0]['id'],'17')
  with self.assertRaises(ValueError):m.drupal_autocomplete([{'label':'no ID','value':'Навчальне'}])
 def test_explicit_empty_query_is_not_a_changed_table_or_protection(self):
  page='<form><input name="formCity"><input name="formStreet"></form><p>Фільтр: Нас. пункт Навчальне + Вулиця ґ</p><strong>Вибраної адреси у графіках не знайдено.</strong>'
  self.assertEqual(m.volyn_rows(page,'Навчальне','ґ'),[])
  for changed in [page.replace('Навчальне','Інше'),page.replace('Вулиця ґ','Вулиця а'),page+'<script>cf-chl-test</script>',page.replace('formCity','other')]:
   with self.assertRaises(ValueError):m.volyn_rows(changed,'Навчальне','ґ')
 def test_discovery_failure_does_not_block_already_discovered_streets(self):
  class HTTP:
   limit=16
   def text(self,url,fields):
    if fields['formStreet']=='ґ':raise ValueError('source changed')
    return '<table><tr><td>Район</td><td>Населений пункт</td><td>Вулиця</td><td>Будинок</td><td>ГПВ</td><td>ГАВ</td></tr><tr><td>Район</td><td>Навчальне</td><td>Нова</td><td>2</td><td>1.2</td><td>7</td></tr></table>'
  rows,observed,_,errors,_=m.volyn(HTTP(),GEO,{'searchTerms':['ґ'],'streetNames':['Нова']})
  self.assertEqual(rows[0]['queue'],'1.2');self.assertEqual(len(observed),1);self.assertEqual(errors[0]['stage'],'street_discovery')
if __name__=='__main__':unittest.main()
