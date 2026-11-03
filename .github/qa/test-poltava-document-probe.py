import datetime as dt
import importlib.util
import unittest
s=importlib.util.spec_from_file_location('probe','.github/qa/poltava-document-probe.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
PDF='https://www.poe.pl.ua/wp-content/uploads/2026/09/source.pdf'
class Probe(unittest.TestCase):
 def test_official_url_scope(self):
  self.assertTrue(m.official_pdf(PDF))
  for u in [PDF.replace('https:','http:'),PDF.replace('www.poe.pl.ua','www.poe.pl.ua.other'),PDF+'?token=x',PDF+'#archive',PDF.replace('www.poe.pl.ua','x@www.poe.pl.ua')]:self.assertFalse(m.official_pdf(u))
 def test_only_live_anchors_not_comments_scripts(self):
  p=m.ActivePDFs();p.feed(f'<!-- <a href="{PDF}">old</a> --><script>var u="{PDF}"</script><a href="{PDF}">now</a>');self.assertEqual(p.links,[PDF])
 def test_archived_containers_and_sections(self):
  p=m.ActivePDFs();p.feed(f'<section class="archive"><a href="{PDF}">old</a></section><h2>Архів</h2><a href="{PDF}">old</a><h2>Чинні документи</h2><a href="{PDF}">current</a>');self.assertEqual(p.links,[PDF])
 def test_explicit_source_period(self):
  now=dt.datetime(2026,11,3,tzinfo=dt.timezone.utc)
  self.assertEqual(m.period('на період з 01.10.2026 року по 01.04.2027 року',now)['status'],'current')
  self.assertEqual(m.period('з 01.10.2025р. по 01.04.2026р.',now)['status'],'not_current')
  self.assertEqual(m.period('file 26_27.pdf',now)['status'],'explicit_period_missing')
 def test_challenge_stops_ordinary_probe(self):
  self.assertTrue(m.challenge('Verify you are human'));self.assertTrue(m.challenge('Just a moment...'))
  self.assertFalse(m.challenge('Інформація про відключення. Cloudflare analytics.'))
if __name__=='__main__':unittest.main()
