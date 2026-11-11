"""Source and user-choice controls; synthetic records never enter the app."""
import copy,datetime,hashlib,importlib.util,json,pathlib,time,unittest
s=importlib.util.spec_from_file_location('historical',pathlib.Path(__file__).with_name('historical-hint-audit.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
NOW=1794391200000
def fixture():
 locality={'name':'Полтава','hromada':'Полтавська','katottg':'UA53101367000096750','streets':{'вулиця Соборності':{'12':['1.2'],'14':['2.1']}}}
 raw=json.dumps({'locality':locality},ensure_ascii=False).encode()
 snapshot={'repository':'reviewed/source','commit':'a'*40,'publishedCommit':'b'*40,'path':'data/source.json','sha256':hashlib.sha256(raw).hexdigest(),'publishedAt':NOW-25*m.DAY,'jsonPointer':'/locality/streets/вулиця Соборності'}
 url='https://raw.githubusercontent.com/reviewed/source/'+snapshot['commit']+'/'+snapshot['path']
 record={'id':'a'*24,'recordVersion':5,'evidenceType':'historical-directory','scope':'house','method':'direct','historical':True,'requiresConfirmation':True,'katottg':locality['katottg'],'settlement':'Полтава','community':'Полтавська','regionId':'UA-53','street':'вулиця Соборності','houses':['12'],'queue':'1.2','operatorId':'poltava','publishedAt':snapshot['publishedAt'],'fetchedAt':NOW-1000,'expiresAt':NOW+m.DAY,'sourceSnapshot':snapshot,'sourceUrl':url,'quote':json.dumps({'вулиця Соборності':{'12':['1.2']}},ensure_ascii=False),'sourceContext':{'verified':True,'basisUrl':url,'jsonPointer':'/locality','settlement':'Полтава','community':'Полтавська','regionId':'UA-53','quote':json.dumps({k:locality[k] for k in ['name','hromada','katottg']},ensure_ascii=False)}}
 return record,raw
def initial():return {'id':'user-created-id','address':'Полтава, вулиця Соборності, 12','addressParts':{'house':'12','street':'вулиця Соборності','city':'Полтава'},'regionId':'UA-53','operatorId':'poltava','queue':None,'queueConfirmed':False,'queueOrigin':None,'reminders':{'enabled':False}}
def accepted(record,stamp):
 return {**initial(),'queue':'1.2','queueConfirmed':True,'queueOrigin':'public','queuePublicHistorical':True,'queueEvidence':'public-historical-directory','queuePublicPublishedAt':record['publishedAt'],'queuePublicObservedAt':record['fetchedAt'],'queuePublicExpiresAt':record['expiresAt'],'queuePublicSnapshot':record['sourceSnapshot'],'queueSource':record['sourceUrl'],'queueUserConfirmedAt':stamp,'queuePublicAddressLabel':m.expected_source_address(record,'12')}
class HistoricalControls(unittest.TestCase):
 def test_original_projection_and_publication_are_independent(self):
  record,raw=fixture();m.validate_record(record,NOW);self.assertTrue(m.verify_source_projection(record,raw)['exactSourceProjectionVerified'])
  publication={'sha':'b'*40,'commit':{'committer':{'date':datetime.datetime.fromtimestamp(record['publishedAt']/1000,datetime.timezone.utc).isoformat()}},'files':[{'filename':'data/source.json','status':'modified'}]}
  self.assertTrue(m.verify_publication(record,json.dumps(publication).encode())['commitSourceVerified'])
  for patch in [{'sha':'c'*40},{'files':[{'filename':'other.json','status':'modified'}]},{'commit':{'committer':{'date':'2026-11-11T00:00:00Z'}}}]:
   with self.subTest(patch=patch),self.assertRaises(ValueError):m.verify_publication(record,json.dumps({**publication,**patch}).encode())
  with self.assertRaises(ValueError):m.verify_source_projection(record,raw+b' ')
  altered=copy.deepcopy(record);altered['sourceSnapshot']['sha256']=hashlib.sha256(raw.replace(b'1.2',b'2.1')).hexdigest()
  with self.assertRaises(ValueError):m.verify_source_projection(altered,raw.replace(b'1.2',b'2.1'))
 def test_manifest_cannot_replace_the_independently_reviewed_source_pin(self):
  record,_=fixture();record['sourceSnapshot']={**m.REVIEWED_SOURCE,'jsonPointer':'/literal/house'};m.require_reviewed_source(record)
  for key in ['commit','sha256','publishedCommit','publishedAt','repository','path']:
   altered=copy.deepcopy(record);altered['sourceSnapshot'][key]='substituted'
   with self.subTest(key=key),self.assertRaises(ValueError):m.require_reviewed_source(altered)
 def test_dates_exact_house_scope_and_lossless_quotes_cannot_be_laundered(self):
  record,_=fixture()
  for patch in [{'publishedAt':NOW},{'fetchedAt':NOW-37*3600000},{'expiresAt':NOW-1},{'expiresAt':NOW+8*m.DAY},{'requiresConfirmation':False},{'houseRanges':['1-99']},{'houses':['12','12']},{'houses':['12-14']},{'queue':'GAV-1'},{'quote':'{}'},{'quote':record['quote']+' '*2501}]:
   with self.subTest(patch=patch),self.assertRaises(ValueError):m.validate_record({**record,**patch},NOW)
 def test_postal_optional_prefix_is_compared_without_changing_or_guessing_context(self):
  value='53101367000096750';self.assertEqual(m.katottg_key(value),m.katottg_key('UA'+value))
  for bad in [int(value),' UA'+value,'ua'+value,'UA'+value+'0',value[:-1],'УА'+value,'UA５３１０１３６７００００９６７５０']:
   with self.subTest(bad=bad),self.assertRaises(ValueError):m.katottg_key(bad)
 def test_pending_candidate_must_not_assign_queue_or_change_literal_source_house(self):
  record,_=fixture();address=m.expected_source_address(record,'12');place=initial();candidate={'id':record['id'],'origin':'public','publicHistorical':True,'publicPublishedAt':record['publishedAt'],'publicObservedAt':record['fetchedAt'],'publicExpiresAt':record['expiresAt'],'sourceUrl':record['sourceUrl'],'publicSnapshot':record['sourceSnapshot'],'queue':'1.2','publicAddressLabel':address};place['queuePublicCandidates']=[candidate]
  m.verify_pending(place,record,address)
  for patch in [{'queue':'1.2'},{'queueConfirmed':True},{'queueOrigin':'official'}]:
   with self.subTest(patch=patch),self.assertRaises(ValueError):m.verify_pending({**place,**patch},record,address)
  for patch in [{'publicAddressLabel':address+'а'},{'publicPublishedAt':NOW},{'publicObservedAt':NOW},{'publicExpiresAt':NOW}]:
   with self.subTest(candidate=patch),self.assertRaises(ValueError):m.verify_pending({**place,'queuePublicCandidates':[{**candidate,**patch}]},record,address)
 def test_refresh_and_restart_preserve_uuid_source_dates_and_explicit_choice_time(self):
  record,_=fixture();stamp=int(time.time()*1000)-100;place=accepted(record,stamp);m.verify_confirmed(place,record,stamp,initial(),stamp)
  for patch in [{'id':'replacement'},{'queueOrigin':'official'},{'queueOrigin':'manual'},{'queueConfirmed':False},{'queueUserConfirmedAt':stamp+1},{'queuePublicPublishedAt':NOW},{'queuePublicObservedAt':NOW},{'queuePublicExpiresAt':NOW},{'queuePublicAddressLabel':place['queuePublicAddressLabel']+'а'},{'reminders':{'enabled':True}}]:
   with self.subTest(patch=patch),self.assertRaises(ValueError):m.verify_confirmed({**place,**patch},record,stamp,initial(),stamp)
 def test_frozen_case_is_never_replaced_and_conflicting_claims_are_not_auto_selected(self):
  record,_=fixture();case={'id':'frozen','city':'Полтава','regionId':'UA-53','exactHouse':'12','exactStreet':'вулиця Соборності'};samples={'frozen.json':{'cases':[case]}}
  self.assertEqual(m.select_case([record],samples,NOW)[1],case)
  for records,case_id in [([record,copy.deepcopy(record)],None),([record],'other')]:
   with self.subTest(case_id=case_id),self.assertRaises(ValueError):m.select_case(records,samples,NOW,case_id)
if __name__=='__main__':unittest.main()
