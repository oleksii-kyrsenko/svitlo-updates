import importlib.util,pathlib,unittest,xml.etree.ElementTree as E
spec=importlib.util.spec_from_file_location('tap_target',pathlib.Path(__file__).with_name('tap_target.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Target(unittest.TestCase):
 def tree(self,bounds='[33,1800][439,1940]',footer='[55,2105][1025,2240]',viewport='[0,231][1080,2075]',extra='',attrs=''):
  return f'<hierarchy><node class="android.widget.ScrollView" scrollable="true" bounds="{viewport}"><node class="android.widget.Button" resource-id="delete-place" content-desc="Видалити адресу" bounds="{bounds}" {attrs}/></node><node resource-id="save-place" bounds="{footer}"/>{extra}</hierarchy>'
 def select(self,**kwargs):return m.delete_target(E.fromstring(self.tree(**kwargs)))
 def test_actual_inverted_clipped_geometry_and_sticky_footer_are_rejected(self):
  for values in [{'bounds':'[33,2223][439,2075]'},{'bounds':'[33,2000][439,2075]'},{'bounds':'[33,2100][439,2200]','viewport':'[0,231][1080,2240]'}, {'bounds':'[33,230][439,400]'},{'attrs':'displayed="false"'},{'attrs':'enabled="false"'},{'bounds':'[-1,1800][439,1940]'}]:
   with self.subTest(values=values):self.assertIsNone(self.select(**values))
 def test_fully_visible_editor_target_is_bound_to_its_scroll_and_footer(self):
  value=self.select();self.assertEqual(value['bounds'],[33,1800,439,1940]);self.assertEqual(value['saveFooter'],[55,2105,1025,2240])
 def test_open_dialog_and_ambiguous_or_missing_footer_prevent_click_selection(self):
  self.assertIsNone(self.select(extra='<node resource-id="delete-place-dialog"/>'))
  self.assertIsNone(self.select(extra='<node resource-id="save-place" bounds="[0,0][10,10]"/>'))
  self.assertIsNone(m.delete_target(E.fromstring(self.tree().replace('resource-id="save-place"','resource-id="other"'))))
 def test_changed_geometry_after_receipt_never_uses_stale_coordinates(self):
  a=self.tree();b=self.tree(bounds='[33,1600][439,1740]');dialog=self.tree(extra='<node resource-id="delete-place-dialog"/>');sequence=iter([a,b,b,b,b,dialog]);clicks=[];receipts=[]
  m.activate_delete(lambda:next(sequence),lambda x,y:clicks.append((x,y)),lambda t:None,lambda *args:receipts.append(args),lambda n:None)
  self.assertEqual(clicks,[(236,1670)]);self.assertTrue(any(r[0]=='tap' and r[2]['bounds']==[33,1600,439,1740] for r in receipts))
 def test_existing_dialog_prevents_any_retap(self):
  dialog=self.tree(extra='<node resource-id="delete-place-dialog"/>');clicks=[]
  m.activate_delete(lambda:dialog,lambda *p:clicks.append(p),lambda t:None,lambda *a:None,lambda n:None);self.assertEqual(clicks,[])
 def test_invisible_button_has_bounded_scrolls_and_no_click(self):
  clicks=[];scrolls=[]
  with self.assertRaisesRegex(AssertionError,'fully visible'):m.activate_delete(lambda:self.tree(bounds='[33,2223][439,2075]'),lambda *p:clicks.append(p),lambda t:scrolls.append(1),lambda *a:None,lambda n:None)
  self.assertEqual(len(scrolls),8);self.assertEqual(clicks,[])
if __name__=='__main__':unittest.main()
