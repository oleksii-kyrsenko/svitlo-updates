import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agents import rotating_sources
class ResearchFairness(unittest.TestCase):
 def test_bounded_runs_eventually_visit_all_sources(self):
  cursors={};seen=set()
  for _ in range(4):seen.update(rotating_sources(list(range(13)),'documents',4,cursors))
  self.assertEqual(seen,set(range(13)))
 def test_explicit_stop_keeps_unprocessed_source_for_next_run(self):
  cursors={}
  for source in rotating_sources(['a','b','c'],'community',3,cursors):
   if source=='b':break
  self.assertEqual(list(rotating_sources(['a','b','c'],'community',1,cursors)),['b'])
 def test_empty_and_shrinking_registry(self):
  cursors={'searches':100};self.assertEqual(list(rotating_sources([],'searches',2,cursors)),[])
  self.assertEqual(list(rotating_sources(['a','b'],'searches',2,cursors)),['a','b'])
if __name__=='__main__':unittest.main()
