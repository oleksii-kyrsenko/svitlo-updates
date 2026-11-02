"""Identity proof for city-regions without invented community names."""
import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from geography import GeographyResolver


class CapitalGeographyTests(unittest.TestCase):
    def city_region(self):
        return {'osm_type': 'relation', 'osm_id': 421866, 'category': 'boundary',
                'type': 'administrative', 'addresstype': 'city', 'place_rank': 8,
                'address': {'country_code': 'ua', 'ISO3166-2-lvl4': 'UA-30', 'city': 'Київ'}}

    def test_city_region_preserves_published_self_identity_without_reverse_guess(self):
        calls = []
        with tempfile.TemporaryDirectory() as folder:
            def fetch(url):
                calls.append(url)
                return [self.city_region()]
            r = GeographyResolver(Path(folder) / 'cache.json', fetcher=fetch,
                                  clock=lambda: 1800000000, rate_interval=0,
                                  rate_path=Path(folder) / 'rate')
            value = r.resolve({'settlement': 'м. Київ', 'regionId': 'UA-30'})
            self.assertEqual(value['community'], 'Київ')
            self.assertEqual(value['communityKind'], 'city-region')
            self.assertEqual(value['cityId'], 'osm-relation-421866')
            self.assertTrue(value['regionUnique'])
            self.assertEqual(len(calls), 1)

    def test_missing_ordinary_municipality_is_never_a_city_region(self):
        original = self.city_region()
        changes = [{'place_rank': 16}, {'osm_type': 'node'}, {'category': 'place'},
                   {'type': 'city'}, {'addresstype': 'town'}, {'osm_id': None},
                   {'address': {**original['address'], 'state': 'Область'}},
                   {'address': {**original['address'], 'country_code': 'pl'}},
                   {'address': {**original['address'], 'ISO3166-2-lvl4': 'UA-32'}}]
        for patch in changes:
            with self.subTest(patch=patch):
                row = {**copy.deepcopy(original), **patch}
                self.assertFalse(GeographyResolver._city_region(row, 'Київ', 'UA-30'))
                self.assertIsNone(GeographyResolver.context_from_record(
                    row, 'Київ', 'UA-30', 'https://nominatim.openstreetmap.org/lookup', 10000))

    def test_regular_community_does_not_claim_region_uniqueness(self):
        row = self.city_region()
        row['place_rank'] = 18
        row['address']['municipality'] = 'Справжня громада'
        result = GeographyResolver.context_from_record(row, 'Київ', 'UA-30', 'https://example.org/geo', 10000)
        self.assertEqual(result['community'], 'Справжня громада')
        self.assertNotIn('regionUnique', result)

    def test_negative_v4_cache_is_rechecked_but_successful_observation_stays_original(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'cache.json'
            key = json.dumps(['geo-v4', 'UA-30', 'київ', None], ensure_ascii=False)
            path.write_text(json.dumps({key: {'expiresAt': 1800001000,
                'result': {'status': 'unresolved', 'reason': 'community_not_published'}}}))
            calls = []
            def fetch(url):
                calls.append(url)
                return [self.city_region()]
            r = GeographyResolver(path, fetcher=fetch, clock=lambda: 1800000000,
                                  rate_interval=0, rate_path=Path(folder) / 'rate')
            self.assertEqual(r.resolve({'settlement': 'Київ', 'regionId': 'UA-30'})['status'], 'resolved')
            self.assertEqual(len(calls), 1)
            path.write_text(json.dumps({key: {'expiresAt': 1800001000, 'result': {
                'status': 'resolved', 'community': 'Київ', 'sourceUrl': 'https://example.org/geo',
                'checkedAt': 1799990000000}}}))
            self.assertEqual(r.resolve({'settlement': 'Київ', 'regionId': 'UA-30'})['checkedAt'], 1799990000000)
            self.assertEqual(len(calls), 1)

    def test_checked_in_targets_are_supported_by_original_source_snapshot(self):
        root = Path(__file__).resolve().parents[2]
        directory = json.loads((root / 'coverage/capital-geography.json').read_text())
        raw = (root / directory['sourceSnapshot']).read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), directory['sourceSnapshotSha256'])
        snapshot = json.loads(raw)
        records = {'osm-' + r['osm_type'] + '-' + str(r['osm_id']): r for r in snapshot['records']}
        self.assertEqual(len(directory['cities']), 22)
        self.assertEqual(len({c['cityId'] for c in directory['cities']}), 22)
        for city in directory['cities']:
            self.assertNotIn(city['regionId'], ['UA-14', 'UA-44', 'UA-43', 'UA-40'])
            record = records[city['cityId']]
            self.assertEqual(city['sourceRecordSha256'], hashlib.sha256(
                json.dumps(record, sort_keys=True, ensure_ascii=False).encode()).hexdigest())
            context = GeographyResolver.context_from_record(record, city['settlement'],
                city['regionId'], city['sourceUrl'], city['checkedAt'])
            self.assertEqual(context['community'], city['community'])
            self.assertEqual(city.get('regionUnique', False), context.get('regionUnique', False))


if __name__ == '__main__':
    unittest.main()
