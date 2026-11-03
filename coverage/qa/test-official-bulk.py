import base64,importlib.util,json,sys,unittest,urllib.parse
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
p=Path(__file__).resolve().parents[1]/'collect-official-bulk.py';s=importlib.util.spec_from_file_location('official_bulk',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
G={'regionId':'UA-61','settlement':'Навчальне','community':'Навчальна міська громада'}
def row(h='1',q='1.1',**extra):return {'city':{'id':7,'name':'Навчальне'},'otg':{'name':'Навчальна'},'street':{'id':8,'name':'вул. Нова'},'buildingNames':h,'chergGpv':q,**extra}
class BulkSafety(unittest.TestCase):
 def test_complete_grouped_public_table_keeps_literal_houses_and_real_source_ids(self):
  rows,obs,completed,meta=m.parse_ternopil([row('1, 3-А, 3/2, 5-9, пляж')],G,'https://example.org/public',1000)
  self.assertEqual([r['houses'][0] for r in rows],['1','3-А','3/2']);self.assertEqual(completed,['7:8']);self.assertTrue(meta['dictionaryComplete']);self.assertEqual(rows[0]['providerCityId'],'7');self.assertEqual(rows[0]['providerStreetId'],'8')
 def test_all_duplicate_connections_unknowns_and_aliases_participate(self):
  rows,obs,_,_=m.parse_ternopil([row('1-А','1.1'),row('1A','2.1'),row('2',''),row('2','1.2'),row('3/2','3.1'),row('32','4.1')],G,'https://example.org',1000)
  self.assertEqual({r['houses'][0]:r['queue'] for r in rows},{'3/2':'3.1','32':'4.1'});self.assertEqual(len(obs),4)
 def test_unexpanded_range_can_block_a_conflicting_literal_house(self):
  rows,_,_,_=m.parse_ternopil([row('1-9','1.1'),row('3, 12','2.1')],G,'https://example.org',1000)
  self.assertEqual([r['houses'][0] for r in rows],['12'])
 def test_city_and_hromada_ambiguity_do_not_become_a_whole_city_guess(self):
  for values in [[row(),row(city={'id':9,'name':'Навчальне'})],[row(otg={'name':'Інша'})]]:
   with self.assertRaises(ValueError):m.parse_ternopil(values,G,'https://example.org',1000)
  with self.assertRaises(ValueError):m.parse_ternopil({'hydra:member':[row()],'hydra:totalItems':2},G,'https://example.org',1000)
 def test_sumy_codec_roundtrip_and_tamper_are_grounded_in_public_client_algorithm(self):
  from cryptography.hazmat.primitives.ciphers.aead import AESGCM
  at=1793688000000;prefix='public-client-codec-example----';iv=b'123456789012';expected={'data':{'result':0,'list':[[7,'місто Навчальне']]}}
  payload=base64.b64encode(iv+AESGCM(m.sumy_key(prefix,at)).encrypt(iv,json.dumps(expected).encode(),None)).decode()
  self.assertEqual(m.decode_sumy({'payload':payload},prefix,at),expected['data'])
  broken=payload[:-4]+'AAAA'
  with self.assertRaises(ValueError):m.decode_sumy({'payload':broken},prefix,at)
 def test_sumy_gpv_is_only_official_column3_not_achr_column1(self):
  g={**G,'regionId':'UA-59'};street={'id':'8','name':'вулиця Нова'}
  values={'result':0,'list':[['м.Навчальне (Навчальна область)','вулиця Нова','1',[None,'4',None,None,None,None,None]],['м.Навчальне','вулиця Нова','2',[None,'4',None,'2.1',None,None,None]]]}
  rows,obs=m.parse_sumy_queue(values,g,7,street,'https://example.org',1000)
  self.assertEqual([(r['houses'],r['queue']) for r in rows],[(['2'],'2.1')]);self.assertEqual(len(obs),2)
 def test_sumy_source_cannot_attach_another_street_or_city(self):
  street={'id':'8','name':'вулиця Нова'}
  for city,name in [('Інше','вулиця Нова'),('Навчальне','вулиця Інша')]:
   with self.assertRaises(ValueError):m.parse_sumy_queue({'result':0,'list':[[city,name,'1',[None,None,None,'1.1',None,None,None]]]},G,7,street,'https://example.org',1000)
 def test_zhytomyr_reads_gpv_columns_and_unknown_connections_without_ignoring_them(self):
  header='<tr>'+''.join('<th>'+s+'</th>' for s in ['РЕМ','Населений пункт','Вулиця','Будинки','Черга','Підчерга','Примітка'])+'</tr>'
  def tr(h,q,sub):return '<tr>'+''.join('<td>'+s+'</td>' for s in ['РЕМ','місто Навчальне','вул. Нова',h,q,sub,''])+'</tr>'
  (rows,obs),count=m.parse_zhytomyr('<table>'+header+tr('1','2','1')+tr('1','Не вимикається','')+tr('2-А','3','2')+'</table>',G,'https://example.org',1000)
  self.assertEqual([(r['houses'],r['queue']) for r in rows],[(['2-А'],'3.2')]);self.assertEqual(len(obs),2)
  with self.assertRaises(ValueError):m.parse_zhytomyr('<table>'+tr('1','2','1')+'</table>',G,'https://example.org',1000)
 def test_bulk_submit_fields_are_read_only_from_offered_anonymous_form(self):
  parsed=m.form('<form id="other"><input type="hidden" name="account" value="private"></form><form id="mainform2"><input type="hidden" name="rem_id" value="7"><input type="submit" name="all" value="показати ще 10 записів"></form>')
  self.assertEqual(parsed.hidden,{'rem_id':'7','all':'показати ще 10 записів'})
class WholeCityBranches(unittest.TestCase):
 def source(self,dep):
  header='<tr>'+''.join('<th>'+x+'</th>' for x in ['РЕМ','Населений пункт','Вулиця','Будинки','Черга','Підчерга','Примітка'])+'</tr>'
  def tr(h,q):return '<tr>'+''.join('<td>'+x+'</td>' for x in ['РЕМ','місто Навчальне','вул. Нова',h,q,'1',''])+'</tr>'
  return '<select name="naspunkt_id"><option value="7">місто Навчальне</option></select><form id="mainform2"><input type="hidden" name="rem_id" value="'+dep+'"><input type="submit" name="all" value="all"></form><table>'+header+tr('1','1' if dep=='a' else '2')+tr('3','3')+'</table>'
 def test_house_consensus_waits_for_all_city_branches(self):
  outer=self
  class Source:
   def text(self,url,fields=None):
    if fields is None:return '<select name="rem_id"><option value="a">Перший</option><option value="b">Другий</option></select>'
    return outer.source(fields['rem_id'])
  rows,obs,_,meta,errors=m.zhytomyr(Source(),G,{})
  self.assertFalse(errors);self.assertTrue(meta['dictionaryComplete']);self.assertEqual([r['houses'] for r in rows],[['3']]);self.assertEqual(len(obs),2)
 def test_partial_branch_discovery_never_publishes_early_city_claim(self):
  outer=self
  class Source:
   def text(self,url,fields=None):
    if fields is None:return '<select name="rem_id"><option value="a">Перший</option><option value="b">Другий</option></select>'
    if fields['rem_id']=='b':raise m.Bound('limit')
    return outer.source('a')
  rows,obs,_,meta,errors=m.zhytomyr(Source(),G,{})
  self.assertFalse(rows);self.assertFalse(obs);self.assertFalse(meta['dictionaryComplete']);self.assertTrue(errors)
 def test_consolidation_preserves_oldest_connection_observation_time(self):
  claim={'cityId':'7','streetId':'8','street':'вул. Нова','houses':['1'],'queue':'1.1','sourceUrl':'https://example.org','checkedAt':1000}
  rows,obs=m.consolidate('sumy',G,[claim,{**claim,'checkedAt':2000}],3000)
  self.assertEqual(rows[0]['checkedAt'],1000);self.assertEqual(rows[0]['expiresAt'],1000+86400000);self.assertEqual(obs[0]['checkedAt'],1000)
class AdaptiveDiscovery(unittest.TestCase):
 def test_source_names_discover_only_streets_not_queues(self):
  names,queries=m.geographic_queries({'elements':[{'tags':{'name':'вулиця Навчальна','outage:queue':'6.2'}},{'tags':{'name':'Нова вулиця'}}]})
  self.assertEqual(names,{'вулиця Навчальна','Нова вулиця'});self.assertIn('Навчальна',queries);self.assertIn('Нова',queries);self.assertNotIn('6.2',queries)
 def test_a_large_request_budget_is_not_limited_to_the_same_first12_terms(self):
  class HTTP:
   limit=40
   def __init__(self):self.calls=0;self.discovered=0
   def json(self,url,headers):
    self.calls+=1;query=urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
    if '/cities?' in url:return {'data':{'result':0,'list':[[7,'Навчальне']]}}
    if '/streets?' in url:
     self.discovered+=1;return {'data':{'result':0,'list':[[self.discovered,'вулиця Навчальна'+str(self.discovered)]]}}
    sid=query['streetId'][0];return {'data':{'result':0,'list':[['Навчальне','вулиця Навчальна'+sid,'1',[None,None,None,'2.1',None,None,None]]]}}
  http=HTTP();state={'streetQueries':['Навчальна'+str(i) for i in range(60)],'streetQueryIndex':0}
  with patch.object(m,'sumy_protocol',return_value=('public-client-prefix',[])),patch.object(m,'source_street_queries',return_value=None):
   rows,obs,_,meta,errors=m.sumy(http,{**G,'regionId':'UA-59'},state)
  self.assertGreater(http.discovered,12);self.assertLessEqual(http.calls,http.limit);self.assertFalse(meta['dictionaryComplete']);self.assertFalse(errors);self.assertEqual(len(rows),len(obs))
class QualifiedBoundaries(unittest.TestCase):
 def test_excluded_house_list_never_becomes_positive_literal_claims(self):
  for text in ['1-15, крім 5, 7','усі, окрім 2, 4','1 під’їзд, 2, 3','частково:1,2,3']:
   self.assertEqual(m.house_parts(text),([],[]))
 def test_unparsed_connection_boundary_blocks_other_literals_on_that_street(self):
  rows,obs,_,_=m.parse_ternopil([row('1-15, крім 5, 7','1.1'),row('5, 7','2.1')],G,'https://example.org',1000)
  self.assertFalse(rows);self.assertEqual(len(obs),2)
if __name__=='__main__':unittest.main()
