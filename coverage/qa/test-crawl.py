import importlib.util,unittest
from pathlib import Path
p=Path(__file__).parents[1]/'collect-asd.py';s=importlib.util.spec_from_file_location('collector',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Tests(unittest.TestCase):
 def setUp(self):
  self.cities=[{'id':i,'name':str(i),'otg':{'name':'community'}} for i in range(1,4)];self.seen=[];self.fail=False
 def fetch(self,path,**v):
  if path=='/pw_streets':return [{'id':i,'name':str(i)} for i in range(1,21)]
  self.seen.append((v['city.id'],v['street.id']))
  if self.fail:raise ValueError('offline')
  return [{'buildingName':'1','chergGpv':'11'}]
 def run_batch(self,state,budget=8):return m.crawl(self.cities,state,budget,1,self.fetch,lambda _:None,now=1000)
 def test_visits_after_first_eight_then_next_city(self):
  state=m.initial_state()
  for _ in range(4):*_,state,examined=self.run_batch(state)
  self.assertEqual(self.seen[:20],[(1,i) for i in sorted(range(1,21),key=str)])
  self.assertEqual(self.seen[20][0],2)
 def test_no_2000_city_ceiling(self):
  self.cities=[{'id':i,'name':str(i)} for i in range(1,2035)];state=m.initial_state();state['cityIndex']=2033
  _,_,_,state,_=self.run_batch(state,1);self.assertEqual(self.seen[0][0],999)
 def test_failure_retries_then_progress_and_later_revisit(self):
  state=m.initial_state();self.fail=True
  for _ in range(3):*_,state,_examined=self.run_batch(state,1)
  self.assertEqual(self.seen[:3],[(1,1)]*3);self.assertEqual(state['streetIndex'],1)
  self.fail=False
  for _ in range(10):*_,state,_examined=self.run_batch(state,50)
  self.assertGreaterEqual(self.seen.count((1,1)),4)
 def test_unknown_success_replaces_whole_street(self):
  def f(path,**values):return [{'id':1,'name':'street'}] if path=='/pw_streets' else [{'buildingName':'1','chergGpv':'Інший ОСР'}]
  rows,completed,_,state,_=m.crawl(self.cities,m.initial_state(),8,1,f,lambda _:None,1000)
  self.assertEqual(rows,[]);self.assertEqual(completed,['1:1']);self.assertEqual(state['cityIndex'],1)
if __name__=='__main__':unittest.main()
