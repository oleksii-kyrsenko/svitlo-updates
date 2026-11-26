"""Synthetic observer controls only; fixtures are never inserted into Android."""
import copy,importlib.util,json,pathlib,unittest
from xml.sax.saxutils import escape,quoteattr
spec=importlib.util.spec_from_file_location('street',pathlib.Path(__file__).with_name('street-controls.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
STAMP=1795673635653
CASE={'city':'Львів','regionId':'UA-46','exactHouse':'52'}
KEY=m.PREFIX+'10:20'
LABEL='Львів, вулиця Дорошенка, 52'
def xml(extra='',button_bounds='[40,500][1000,610]',warning_bounds='[40,410][1000,475]',button_attr='',card_attr='',form_bounds='[0,100][1080,2200]'):
 return '<hierarchy><node resource-id="address-form" bounds="'+form_bounds+'"><node bounds="[20,250][1020,650]" '+card_attr+'><node text='+quoteattr(next(iter(m.SELECTION_MESSAGES)))+' bounds="[40,290][1000,390]"/><node text='+quoteattr(m.WARNING)+' bounds="'+warning_bounds+'"/><node resource-id="'+KEY+'" content-desc='+quoteattr(LABEL)+' bounds="'+button_bounds+'" enabled="true" '+button_attr+'/>'+extra+'</node></node></hierarchy>'
def fixture():
 source={'id':'|10:20','street':'вулиця Дорошенка','sourceUrl':'https://poweron.loe.lviv.ua/','providerCityId':None}
 context={'regionId':'UA-46','community':'Львівська громада','district':'Львівський район','katottg':'46100000000000000'}
 address=['lviv','UA-46','львів','львівська громада','львівський район','UA46100000000000000','postal-street','петра дорошенка','52','']
 marker={'version':1,'selectedAt':STAMP,'addressIdentity':json.dumps(address,ensure_ascii=False,separators=(',',':')),'source':source}
 place={'id':'real-user-created-uuid','address':'Львів, вулиця Петра Дорошенка, 52','addressOrigin':'postal','addressParts':{'settlement':'Львів','street':'вулиця Петра Дорошенка','house':'52'},'addressSelection':{'street':{'id':'postal-street'}},'addressContext':context,'regionId':'UA-46','operatorId':'lviv','officialCityId':'10:20','officialAddress':LABEL,'queue':'1.1','queueOrigin':'official','queueConfirmed':True,'queueStreetResolution':'user_selected','queueStreetSelectedAt':STAMP,'queueStreetSelection':marker,'queueSource':source['sourceUrl'],'reminders':{'enabled':False}}
 choice={'buttonId':KEY,'sourceLabel':LABEL,'sourceStreet':'вулиця Дорошенка'}
 return place,choice
class StreetControls(unittest.TestCase):
 def test_home_top_is_actual_contained_card_and_stops_scroll_before_pull_to_refresh(self):
  value='<hierarchy><node resource-id="main-scroll" bounds="[0,100][1080,2200]"><node resource-id="current-address-card" bounds="[20,110][1060,400]"/></node></hierarchy>'
  self.assertTrue(m.home_top_visible(value,1080,2340))
  for changed in [value.replace('[20,110]','[20,90]'),value.replace('resource-id="current-address-card"','resource-id="another-card"'),value.replace('bounds="[20,110]','displayed="false" bounds="[20,110]'),value.replace('bounds="[0,100]','visible-to-user="false" bounds="[0,100]')]:
   with self.subTest(xml=changed):self.assertFalse(m.home_top_visible(changed,1080,2340))
 def test_visible_unique_warning_status_button_and_literal_house(self):
  value=m.visible_choice(xml(),KEY,'52',1080,2340);self.assertEqual(value['sourceHouse'],'52');self.assertEqual(value['observedSelectionStatus'],'needs_selection')
 def test_nearby_suffix_fraction_or_middle_address_number_cannot_prove_house(self):
  for label in ['Львів, вулиця 52-го кварталу, 520','Львів, вулиця Дорошенка, 52а','Львів, вулиця Дорошенка, 52/1','Львів, вулиця Дорошенка']:
   with self.subTest(label=label),self.assertRaises(ValueError):m.visible_choice(xml().replace(quoteattr(LABEL),quoteattr(label)),KEY,'52',1080,2340)
 def test_hidden_clipped_disabled_or_unrelated_warning_does_not_bind(self):
  variants=[xml(button_attr='displayed="false"'),xml(card_attr='visible-to-user="false"'),xml(button_bounds='[40,2180][1000,2280]'),xml(button_bounds='[40,500][1081,610]'),xml(warning_bounds='[40,250][1000,300]'),xml(form_bounds='[0,100][1080,550]'),xml().replace('enabled="true"','enabled="false"'),xml().replace(m.WARNING,'Завантажуємо джерело')]
  for value in variants:
   with self.subTest(xml=value),self.assertRaises(ValueError):m.visible_choice(value,KEY,'52',1080,2340)
 def test_second_choice_is_never_replaced_with_first_visible_button(self):
  value=xml(extra='<node resource-id="'+m.PREFIX+'10:21" content-desc="Львів, інша вулиця, 52" bounds="[40,2400][1000,2500]"/>')
  with self.assertRaises(ValueError):m.visible_choice(value,KEY,'52',1080,2340)
 def test_status_must_be_visible_needs_selection_and_queue_must_be_user_selected(self):
  with self.assertRaises(ValueError):m.visible_choice(xml().replace(next(iter(m.SELECTION_MESSAGES)),'Інший статус'),KEY,'52',1080,2340)
  ready=xml(extra='<node text="Черга 1.1 · за вибраним вами записом оператора" bounds="[40,620][1000,680]"/>')
  with self.assertRaises(ValueError):m.visible_choice(ready,KEY,'52',1080,2340)
  self.assertEqual(m.visible_selected_queue(ready,1080,2340),'1.1')
  self.assertIsNone(m.visible_selected_queue(ready.replace('за вибраним вами записом оператора','знайдено автоматично'),1080,2340))
 def test_original_marker_uses_all_address_and_geography_fields(self):
  place,choice=fixture();self.assertEqual(m.validate_ready(place,CASE,choice,[STAMP-10,STAMP+10],'1.1'),place['queueStreetSelection'])
  for index,replacement in [(0,'ternopil'),(1,'UA-61'),(2,'київ'),(3,'інша громада'),(4,'інший район'),(5,'UA46100000000000001'),(6,'other-postal-street'),(7,'інша вулиця'),(8,'520'),(9,'changed-connection')]:
   altered=copy.deepcopy(place);address=json.loads(altered['queueStreetSelection']['addressIdentity']);address[index]=replacement;altered['queueStreetSelection']['addressIdentity']=json.dumps(address)
   with self.subTest(index=index),self.assertRaises(ValueError):m.validate_marker(altered,CASE,choice,[STAMP-10,STAMP+10])
 def test_android_window_rejects_missing_past_future_or_nonfinite_consent(self):
  place,choice=fixture()
  for stamp in [None,True,float('nan'),float('inf'),STAMP-11,STAMP+11]:
   altered=copy.deepcopy(place);altered['queueStreetSelection']['selectedAt']=stamp
   with self.subTest(stamp=stamp),self.assertRaises(ValueError):m.validate_marker(altered,CASE,choice,[STAMP-10,STAMP+10])
 def test_source_marker_routing_url_and_actual_clicked_street_are_bound(self):
  place,choice=fixture()
  for field,value in [('id','|10:21'),('street','вулиця Петра Дорошенка'),('sourceUrl','http://poweron.loe.lviv.ua/'),('sourceUrl','https://user:password@poweron.loe.lviv.ua/'),('providerCityId','another-city')]:
   altered=copy.deepcopy(place);altered['queueStreetSelection']['source'][field]=value
   with self.subTest(field=field,value=value),self.assertRaises(ValueError):m.validate_marker(altered,CASE,choice,[STAMP-10,STAMP+10])
  altered=copy.deepcopy(place);altered['officialCityId']='10:21'
  with self.assertRaises(ValueError):m.validate_marker(altered,CASE,choice,[STAMP-10,STAMP+10])
 def test_official_queue_cannot_be_promoted_to_automatic_or_manual(self):
  place,choice=fixture()
  for patch in [{'queueOrigin':'manual'},{'queueStreetResolution':'automatic'},{'queueConfirmed':False},{'queue':'2.1'},{'queueStreetSelectedAt':STAMP+1},{'queueSource':'https://another.example/'}]:
   with self.subTest(patch=patch),self.assertRaises(ValueError):m.validate_ready({**place,**patch},CASE,choice,[STAMP-10,STAMP+10],'1.1')
 def test_offline_preserves_uuid_markers_settings_and_existing_ready_cache(self):
  place,choice=fixture();state={'places':[place],'activePlaceId':place['id'],'notificationsEnabled':False,'gpsAsked':True,'snapshots':{place['id']:{'today':{'status':'ready','checkedAt':100,'validUntil':200,'intervals':[[10,20]]}}}};before=m.projected(state,{'theme':'aurora'});after=copy.deepcopy(before)
  m.unchanged_saved(before,after);after['cache']['today']['refreshError']={'status':'source_unavailable'};self.assertEqual(m.unchanged_ready_cache(before['cache'],after['cache'])['readyDaysPreserved'],['today'])
  for field,value in [('activePlaceId','replacement'),('settings',{'notificationsEnabled':True}),('appearance',{'theme':'moss'})]:
   changed=copy.deepcopy(after);changed[field]=value
   with self.subTest(field=field),self.assertRaises(ValueError):m.unchanged_saved(before,changed)
  for field in ['queueStreetSelection','officialCityId','queue','addressParts','reminders']:
   changed=copy.deepcopy(after);changed['place'][field]='changed'
   with self.subTest(field=field),self.assertRaises(ValueError):m.unchanged_saved(before,changed)
  after['cache']['today']['checkedAt']=101
  with self.assertRaises(ValueError):m.unchanged_ready_cache(before['cache'],after['cache'])
  self.assertEqual(m.unchanged_ready_cache(None,None)['status'],'NOT_PRESENT')
if __name__=='__main__':unittest.main()
