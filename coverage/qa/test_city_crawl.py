import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from city_crawl import city_key,select_city,search_inventory,request_limit,scoped_state
class CityCrawlSafety(unittest.TestCase):
 def test_locality_types_and_hromada_do_not_hide_a_capital(self):
  self.assertEqual(city_key('м.Одеса'),'одеса')
  self.assertEqual(city_key('м. Хмельницький (Хмельницька міська громада)'),'хмельницький')
  self.assertRaises(ValueError,select_city,[{'name':'м. Львів'},{'name':'Львів'}],'Львів')
  self.assertRaises(ValueError,select_city,[{'name':'Інше місто'}],'Львів')
 def test_capped_autocomplete_retains_frontier_and_discovers_tail(self):
  state={};calls=[]
  def fetch(term):
   calls.append(term)
   return [{'id':1,'value':'А'},{'id':2,'value':'Б'}] if term=='' else [{'id':3,'value':'В'}]
  first=search_inventory(fetch,state,cap=2,initial_queries=[''],max_queries=1)
  self.assertEqual(len(first),2);self.assertTrue(state['queries'])
  self.assertEqual(len(search_inventory(fetch,state,cap=2,initial_queries=[''],max_queries=1)),3)
  self.assertEqual(calls[0],'');self.assertNotEqual(calls[1],'')
 def test_failed_dictionary_keeps_the_same_query_for_resume(self):
  state={}
  def fail(term):raise OSError('source failure')
  self.assertRaises(OSError,search_inventory,fail,state,cap=20,initial_queries=['Нова'])
  self.assertEqual(state['queries'],['Нова']);self.assertEqual(state['done'],[])
 def test_city_cursors_do_not_overwrite_existing_live_cursor(self):
  legacy={'streetIndex':90};city=scoped_state(legacy,'м.Львів',True);city['streetIndex']=3
  self.assertEqual(legacy['streetIndex'],90);self.assertEqual(scoped_state(legacy,'Львів',True)['streetIndex'],3)
 def test_cli_request_budget_is_numeric_bounded(self):
  self.assertEqual(request_limit('120'),120)
  for value in ['0','2001','oops']:self.assertRaises(ValueError,request_limit,value)
if __name__=='__main__':unittest.main()
