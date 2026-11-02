"""Regression: elongated city geometry must not erase its other outskirts."""
import math,pathlib,sys,tempfile,json,unittest
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'capitals'))
from holdout import choose_city,quadrant,validate_candidate
from common import distance_km,street_identity,digest

class SelectionTests(unittest.TestCase):
 def point(self,angle,radius,index):
  lat=49+radius*math.cos(math.radians(angle))/111.32
  lon=30+radius*math.sin(math.radians(angle))/(111.32*math.cos(math.radians(49)))
  return {'regionId':'UA-05','city':'Зразок','latitude':lat,'longitude':lon,'osmType':'way','osmId':index,'exactStreet':f'вулиця Зразкова {index}','exactHouse':'7','selectedWithoutQueueData':True}
 def test_outskirts_are_relative_to_each_direction_not_the_longest_arm(self):
  city={'regionId':'UA-05','city':'Зразок','centerLatitude':49,'centerLongitude':30,'regionQuery':'Зразкова','cityOsmRelation':1}
  rows=[self.point(i*45,1.1,i+1) for i in range(8)]
  rows += [self.point(q*90+10+i*8,(14 if q==1 else 4)+i*.35,100+q*10+i) for q in range(4) for i in range(6)]
  with patch('holdout.validate_candidate'):
   selected,rejected=choose_city(city,rows,[],'.')
  self.assertEqual(len(selected),20)
  self.assertEqual(sum(c['zone']=='center' for c in selected),8)
  outskirts=[c for c in selected if c['zone']=='periphery']
  self.assertEqual(len(outskirts),12)
  self.assertGreaterEqual(len({quadrant(c,city) for c in outskirts}),3)
  self.assertEqual(len({street_identity(c['exactStreet']) for c in selected}),20)
  self.assertTrue(all(distance_km(a,b)>=.25 for i,a in enumerate(selected) for b in selected[i+1:]))
 def test_exact_building_lookup_still_requires_region_and_city(self):
  case=self.point(45,1,7);city={'regionId':'UA-05','city':'Зразок'}
  original={'osm_type':'way','osm_id':7,'lat':case['latitude'],'lon':case['longitude'],'address':{'country_code':'ua','city':'Зразок','road':case['exactStreet'],'house_number':'7','ISO3166-2-lvl4':'UA-07'}}
  with tempfile.TemporaryDirectory() as tmp:
   path=pathlib.Path(tmp)/'original.json';path.write_text(json.dumps([original]))
   case['verification']={'method':'nominatim-address','sourceUrl':'https://nominatim.openstreetmap.org/lookup?osm_ids=W7','checkedAt':'2026-11-02T12:00:00Z','artifact':{'path':'original.json','sha256':digest(path.read_bytes())}}
   with self.assertRaisesRegex(ValueError,'region membership'):validate_candidate(case,city,tmp)
   original['address']['ISO3166-2-lvl4']='UA-05';path.write_text(json.dumps([original]));case['verification']['artifact']['sha256']=digest(path.read_bytes());validate_candidate(case,city,tmp)
if __name__=='__main__':unittest.main()
