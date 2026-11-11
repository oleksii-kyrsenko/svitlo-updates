"""Negative controls against page-wide, clipped and wrong-card UI evidence."""
import importlib.util,pathlib,unittest,xml.etree.ElementTree as ET
s=importlib.util.spec_from_file_location('screen',pathlib.Path(__file__).with_name('historical-screen.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
def tree(flattened=False):
 root=ET.Element('hierarchy');scroll=ET.SubElement(root,'node',{'resource-id':'app:id/main-scroll','bounds':'[0,100][1080,2100]'})
 scope=ET.SubElement(scroll,'node',{'resource-id':'app:id/public-candidate-id','bounds':'[30,150][1050,700]'})
 target=scroll if flattened else scope
 ET.SubElement(target,'node',{'text':'source warning','bounds':'[50,200][1000,270]'})
 ET.SubElement(scroll,'node',{'text':'unrelated footer original date','bounds':'[30,800][1050,900]'})
 return root,scroll,scope,target
def capture(root):return m.visible_notice(ET.tostring(root,encoding='unicode'),'public-candidate-id',1080,2340)
class HistoricalScreen(unittest.TestCase):
 def test_descendant_and_flattened_android_views_bind_only_the_exact_card(self):
  for flattened in [False,True]:
   with self.subTest(flattened=flattened):
    root,_,_,_=tree(flattened);self.assertEqual(capture(root)['texts'],['source warning']);self.assertIn('historical',capture(root)['binding'])
 def test_hidden_offscreen_clipped_and_zero_area_labels_do_not_prove_visibility(self):
  for patch in [{'visible-to-user':'false'},{'displayed':'false'},{'bounds':'[50,-40][1000,270]'},{'bounds':'[50,200][1051,270]'},{'bounds':'[50,200][50,270]'},{'bounds':'[50,200][1000,2400]'}]:
   with self.subTest(patch=patch):
    root,_,_,target=tree();target[0].attrib.update(patch);self.assertEqual(capture(root)['texts'],[])
 def test_missing_duplicate_or_wrong_scroll_container_fails_closed(self):
  root,scroll,scope,_=tree();scroll.append(ET.fromstring(ET.tostring(scope)));self.assertEqual(capture(root)['texts'],[])
  root,scroll,_,_=tree();scroll.set('resource-id','other-scroll');self.assertEqual(capture(root)['texts'],[])
  root,_,scope,_=tree();scope.set('resource-id','public-candidate-other');self.assertEqual(capture(root)['texts'],[])
 def test_hidden_ancestor_cannot_supply_a_notice(self):
  root,scroll,_,_=tree();scroll.set('displayed','false');self.assertEqual(capture(root)['texts'],[])
 def test_partially_scrolled_container_accepts_only_fully_visible_text(self):
  root,_,scope,target=tree();scope.set('bounds','[30,-100][1050,700]');ET.SubElement(target,'node',{'text':'clipped','bounds':'[50,50][1000,130]'});self.assertEqual(capture(root)['texts'],['source warning'])
if __name__=='__main__':unittest.main()
