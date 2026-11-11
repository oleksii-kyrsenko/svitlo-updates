import importlib.util,pathlib,tempfile,unittest
spec=importlib.util.spec_from_file_location('screen',pathlib.Path(__file__).with_name('screen.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Screen(unittest.TestCase):
 def fixture(self,extra='',flat=True,label='12:00 — 15:00',text_bounds='[40,420][900,480]'):
  text=f'<android.widget.TextView text="{label}" bounds="{text_bounds}"/>'
  graph=f'<android.view.View resource-id="schedule-graph" bounds="[20,300][1000,1600]">{text if not flat else ""}</android.view.View>'
  return '<hierarchy><android.widget.TextView text="12:00 — 15:00" bounds="[40,0][900,40]"/><android.view.View resource-id="main-scroll" bounds="[0,200][1080,1800]">'+graph+(text if flat else '')+extra+'</android.view.View></hierarchy>'
 def test_helper_loader_never_executes_scenario(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)/'helpers.py';p.write_text('def sentinel():return 1\nflags={}\nraise AssertionError("must not run APK scenario")\n')
   self.assertEqual(m.load_helpers(p)['sentinel'](),1)
 def test_real_class_flattened_sibling_and_descendant_shapes(self):
  for flat in [True,False]:
   result=m.graph_evidence(self.fixture(flat=flat),[720,900]);self.assertEqual(result['interval'],[720,900])
 def test_system_clock_outside_other_card_hidden_clipped_or_wrong_range_cannot_prove_interval(self):
  variants=[self.fixture(label='no interval'),self.fixture(text_bounds='[40,1700][900,1760]'),self.fixture(text_bounds='[40,170][900,250]'),self.fixture(label='12:00 — 14:00'),self.fixture().replace('text="12:00 — 15:00" bounds="[40,420]', 'displayed="false" text="12:00 — 15:00" bounds="[40,420]')]
  for value in variants:
   with self.subTest(xml=value):self.assertIsNone(m.graph_evidence(value,[720,900]))
 def test_heading_must_be_actual_graph_text(self):
  self.assertIsNone(m.graph_evidence(self.fixture(label='other',extra='<android.widget.TextView text="Графік на добу" bounds="[40,1700][900,1760]"/>')))
  self.assertIsNotNone(m.graph_evidence(self.fixture(label='Графік на добу')))
 def test_bad_or_multiple_graph_bounds_fail_closed(self):
  self.assertIsNone(m.graph_evidence(self.fixture().replace('[20,300][1000,1600]','[20,300][20,1600]'),[720,900]))
  self.assertIsNone(m.graph_evidence(self.fixture(extra='<android.view.View resource-id="schedule-graph" bounds="[20,300][1000,1600]"/>'),[720,900]))
if __name__=='__main__':unittest.main()
