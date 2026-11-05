import importlib.util,json,tempfile,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('cache',Path(__file__).resolve().parents[1]/'cache-zap-app-authority.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class AuthorityCache(unittest.TestCase):
 def fixture(self,folder,method='current-live-official-parent'):
  url='https://script.google.com/macros/s/reviewed/exec';label='Дізнатися свою чергу по м. Запоріжжя'
  raw=('<a href="'+url+'">'+label+'</a>').encode()
  for name in ['official-parent-attempt.html','reviewed-authority-original.html']:(folder/name).write_bytes(raw)
  functions={'loadData':'streetData=data;getData()','loadHouses':'row[0] === street;row[1]','showQueue':'row[0] === street && row[1] === house;gpvQueue=row[2];zova=row[3];gavQueue=row[4]'}
  frontend=json.dumps(functions).encode();(folder/'official-public-frontend-functions.json').write_bytes(frontend)
  p={'schemaVersion':1,'operatorId':'zaporizhzhia','regionId':'UA-23','settlement':'Запоріжжя','sourceUrl':url,'checkedAt':2000,'expiresAt':86401000,'officialCityScopeLabel':label,'authority':{'sourceUrl':m.decoder.PARENT,'checkedAt':1000,'expiresAt':86401000,'sha256':m.decoder.sha(raw),'method':method},'frontendSchema':{'sourceUrl':url,'sha256':m.decoder.sha(frontend),'GPVcolumn':2,'partialExemptionsColumn':3,'GAVcolumnNeverSubstituted':4}}
  return p,{'reviewedPublicAppUrl':url},raw
 def test_fresh_parent_keeps_actual_original_clock_and_bytes(self):
  with tempfile.TemporaryDirectory() as d:
   folder=Path(d);p,r,raw=self.fixture(folder);body,meta=m.cache_plan(p,folder/'projection.json',r,3000)
   self.assertEqual(body,raw);self.assertEqual(meta['checkedAt'],1000);self.assertEqual(meta['expiresAt'],86401000)
 def test_temporary_fallback_never_yields_a_cache_renewal(self):
  with tempfile.TemporaryDirectory() as d:
   folder=Path(d);p,r,_=self.fixture(folder,'previously-reviewed-official-parent-during-temporary-unavailability')
   self.assertIsNone(m.cache_plan(p,folder/'projection.json',r,3000))
 def test_expired_original_and_changed_or_removed_deployment_fail_closed(self):
  with tempfile.TemporaryDirectory() as d:
   folder=Path(d);p,r,_=self.fixture(folder)
   with self.assertRaises(ValueError):m.cache_plan(p,folder/'projection.json',r,86401000)
   with self.assertRaisesRegex(ValueError,'unreviewed_public_app_deployment'):m.cache_plan(p,folder/'projection.json',{'reviewedPublicAppUrl':r['reviewedPublicAppUrl'].replace('reviewed/','another/')},3000)
   raw=b'<html>current link removed</html>';(folder/'official-parent-attempt.html').write_bytes(raw);p['authority']['sha256']=m.decoder.sha(raw)
   with self.assertRaises(ValueError):m.cache_plan(p,folder/'projection.json',r,3000)
 def test_unknown_authority_method_does_not_renew(self):
  with tempfile.TemporaryDirectory() as d:
   folder=Path(d);p,r,_=self.fixture(folder,'unverified-cache')
   with self.assertRaisesRegex(ValueError,'unknown_authority_observation_method'):m.cache_plan(p,folder/'projection.json',r,3000)

if __name__=='__main__':unittest.main()
