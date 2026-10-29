import unittest,sys,pathlib,datetime
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'directory'))
from reader import observe,street_links
class Directory(unittest.TestCase):
 source={'url':'https://energy-ua.info/select/%D1%81.%2BТестове','sourceSettlement':'с. Тестове','settlement':'Тестове','community':'Тестова','regionName':'Полтавська область','regionId':'UA-53','operatorId':'poltava','geographyBasisUrl':'https://example.invalid/community'}
 url='https://energy-ua.info/grafik/%D1%81.%2BТестове/Садова'
 now=int(datetime.datetime(2026,10,29,8,tzinfo=datetime.timezone.utc).timestamp()*1000)
 html='<h1>Графік відключення електроенергії с. Тестове, Садова</h1><p class="ch_num_info">У вас <b>2 черга (1 підгрупа)</b> - після підключення сповіщень орієнтуйтесь на неї!</p><span class="scale_info_ch_date">Чт. 29.10.2026</span>'
 def test_current_live_directory_is_observation_not_new_publication(self):
  r=observe(self.html,self.url,'Садова',self.source,self.now);self.assertEqual(r['queue'],'2.1');self.assertEqual(r['scope'],'street');self.assertIsNone(r['publishedAt']);self.assertEqual(r['fetchedAt'],self.now);self.assertLessEqual(r['expiresAt']-self.now,12*3600000)
 def test_old_graph_and_wrong_locality_are_rejected(self):
  self.assertIsNone(observe(self.html.replace('29.10.2026','28.10.2026'),self.url,'Садова',self.source,self.now));self.assertIsNone(observe(self.html.replace('Тестове','Інше'),self.url,'Садова',self.source,self.now))
 def test_house_selector_and_qualified_street_are_not_whole_street(self):
  self.assertIsNone(observe(self.html,self.url+'/10','Садова',self.source,self.now));self.assertIsNone(observe(self.html,self.url+'%20непарні','Садова непарні',self.source,self.now))
 def test_directory_links_preserve_locality_and_do_not_expand_house_lists(self):
  body='<h1>Графік відключення електроенергії с. Тестове (Полтавська область)</h1><a href="'+self.url+'">Садова</a><a href="'+self.url+'/10">10</a><a href="https://energy-ua.info/grafik/Інше/Садова">Садова</a>'
  self.assertEqual(street_links(body,self.source),[{'url':self.url,'label':'Садова'}])
 def test_expiry_stops_at_kyiv_midnight(self):
  now=int(datetime.datetime(2026,10,29,21,30,tzinfo=datetime.timezone.utc).timestamp()*1000);r=observe(self.html,self.url,'Садова',self.source,now);self.assertEqual(r['expiresAt']-now,30*60000)
 def test_house_selection_alias_prevents_blanket_street_assignment(self):
  body='<h1>Графік відключення електроенергії с. Тестове (Полтавська область)</h1><a href="'+self.url+'">Садова</a><a href="https://energy-ua.info/select/%D1%81.%2BТестове/вул.%2BСадова">вул. Садова</a>'
  self.assertEqual(street_links(body,self.source),[])
 def test_partial_street_alias_cannot_be_hidden_by_scan_window(self):
  body='<h1>Графік відключення електроенергії с. Тестове (Полтавська область)</h1><a href="'+self.url+'">Садова</a><a href="'+self.url+'%28непарні%29">Садова(непарні)</a>'
  self.assertEqual(street_links(body,self.source),[])
 def test_numeric_house_tail_invalidates_a_whole_street_alias(self):
  body='<h1>Графік відключення електроенергії с. Тестове (Полтавська область)</h1><a href="'+self.url+'">Садова</a><a href="'+self.url+'%2C1-25">Садова,1-25</a>'
  self.assertEqual(street_links(body,self.source),[])
 def test_combined_street_label_invalidates_component_blanket_claims(self):
  body='<h1>Графік відключення електроенергії с. Тестове (Полтавська область)</h1><a href="'+self.url+'">Садова</a><a href="'+self.url+'%2CМиру">Садова,Миру</a>'
  self.assertEqual(street_links(body,self.source),[])
if __name__=='__main__':unittest.main()
