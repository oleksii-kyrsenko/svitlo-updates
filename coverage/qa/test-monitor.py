import importlib.util,unittest
from pathlib import Path
p=Path(__file__).parents[1]/'monitor.py';s=importlib.util.spec_from_file_location('monitor',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Tests(unittest.TestCase):
 def test_challenge_is_not_success(self):self.assertEqual(m.classify(200,'<script src="/cdn-cgi/challenge-platform/"></script>'),'source_protected')
 def test_ok_is_only_availability(self):self.assertEqual(m.classify(200,'page'),'page_available')
 def test_discovery_never_makes_queue(self):
  p=m.Links('https://example.org/');p.feed('<a href="https://t.me/channel">channel</a><a href="/list.pdf">doc</a><a href="javascript:alert(1)">bad</a>');self.assertEqual(len(p.links),2)
if __name__=='__main__':unittest.main()
