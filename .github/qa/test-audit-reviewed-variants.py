"""Previously reviewed display labels never replace frozen geographic identity."""
import copy,hashlib,importlib.util,json,pathlib,tempfile,unittest

ROOT=pathlib.Path(__file__).parent
spec=importlib.util.spec_from_file_location('reviewed_address_audit',ROOT/'national-address-audit.py');audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)

class ReviewedDisplayVariants(unittest.TestCase):
    def setUp(self):
        self.baseline_raw=(ROOT/'capital-baseline.json').read_bytes()
        self.original=json.loads(self.baseline_raw)['cases']
        self.metadata=json.loads((ROOT/'capital-reviewed-display-variants.json').read_bytes())
        self.cases,self.alias_sha,_=audit.attach_reviewed_display_variants(self.original,hashlib.sha256(self.baseline_raw).hexdigest())
        self.lviv=next(c for c in self.cases if c['id']=='UA-46-capital-2')
    def test_only_original_three_cases_receive_aliases_without_mutating_sample(self):
        self.assertEqual({c['id'] for c in self.cases if c.get('reviewedDisplayStreetVariants')},audit.REVIEWED_CASE_IDS)
        self.assertEqual(self.baseline_raw,(ROOT/'capital-baseline.json').read_bytes())
        for original,derived in zip(self.original,self.cases):
            self.assertNotIn('reviewedDisplayStreetVariants',original)
            for key in ['id','city','exactStreet','exactHouse','osmType','osmId','latitude','longitude']:
                self.assertEqual(original[key],derived[key])
    def test_exact_metadata_bytes_are_pinned(self):
        self.assertEqual(self.alias_sha,'5bf4f083c9740e4f552acd39ed668f8a9d01cf2b0c50c437b0d88a7bfc57c8df')
        with tempfile.TemporaryDirectory() as tmp:
            path=pathlib.Path(tmp)/'aliases.json';path.write_text(json.dumps(self.metadata))
            self.assertRaisesRegex(ValueError,'pinned review',audit.attach_reviewed_display_variants,self.original,audit.REVIEWED_BASELINE_SHA256,path)
    def test_short_lviv_label_is_used_by_query_selection_and_saved_validation(self):
        variants=audit.case_street_variants(self.lviv)
        self.assertIn('дорошенка',audit.case_street_queries(self.lviv))
        self.assertTrue(any(audit.street_matches('вулиця Дорошенка',v) for v in variants))
        place={'addressOrigin':'postal','addressParts':{'settlement':'Львів','street':'вулиця Дорошенка','house':'52'},'addressSelection':{'city':{'id':'city'},'street':{'id':'street'},'house':{'id':'house'}}}
        audit.validate_saved_address(self.lviv,{},place)
        original=next(c for c in self.original if c['id']==self.lviv['id'])
        self.assertRaises(RuntimeError,audit.validate_saved_address,original,{},place)
        changed=copy.deepcopy(place);changed['addressParts']['house']='53'
        self.assertRaisesRegex(RuntimeError,'house',audit.validate_saved_address,self.lviv,{},changed)
    def test_reviewed_short_label_requires_same_osm_building_and_house(self):
        for patch in [{'osmId':1},{'osmType':'node'},{'exactHouse':'53'}]:
            cases=copy.deepcopy(self.original);target=next(c for c in cases if c['id']=='UA-46-capital-2');target.update(patch)
            self.assertRaisesRegex(ValueError,'frozen OSM',audit.validate_reviewed_display_metadata,self.metadata,cases)
    def test_metadata_cannot_change_street_type_or_add_house_or_person(self):
        for variant in ['провулок Дорошенка','вулиця Дорошенка 53','вулиця Іншого Дорошенка']:
            metadata=copy.deepcopy(self.metadata);metadata['variants']['UA-46-capital-2'][0]=variant
            self.assertRaises(ValueError,audit.validate_reviewed_display_metadata,metadata,self.original)
        metadata=copy.deepcopy(self.metadata);metadata['lvivShortNameEvidence']['sameFrozenOsmId']=999
        self.assertRaises(ValueError,audit.validate_reviewed_display_metadata,metadata,self.original)
        metadata=copy.deepcopy(self.metadata);metadata['variants']['UA-73-capital-3']=['вулиця Нова']
        self.assertRaises(ValueError,audit.validate_reviewed_display_metadata,metadata,self.original)
    def test_holdout_cannot_inherit_baseline_name_exceptions(self):
        raw=(ROOT/'capital-holdout.json').read_bytes();holdout=json.loads(raw)['cases']
        holdout[0]['reviewedDisplayStreetVariants']=['вулиця Дорошенка'];holdout[0]['reviewedDisplayVariantsSha256']=audit.REVIEWED_DISPLAY_VARIANTS_SHA256
        cases,sha,_=audit.attach_reviewed_display_variants(holdout,hashlib.sha256(raw).hexdigest())
        self.assertEqual(len(cases),440);self.assertEqual(sha,self.alias_sha)
        self.assertFalse(any(c.get('reviewedDisplayStreetVariants') for c in cases))
    def test_unpinned_case_field_does_not_enable_an_arbitrary_short_label(self):
        case=copy.deepcopy(self.lviv);case['reviewedDisplayVariantsSha256']='0'*64
        self.assertNotIn('вулиця Дорошенка',audit.case_street_variants(case))

if __name__=='__main__':unittest.main()
