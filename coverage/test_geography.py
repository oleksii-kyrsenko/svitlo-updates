import json
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from geography import GeographyResolver

class GeographyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.at = 1800000000.0
        self.calls = []
        self.query = {'settlement': 'Зразкове', 'regionId': 'UA-46'}

    def resolver(self, responses, **kwargs):
        def fetch(url):
            self.calls.append(url)
            response = responses.pop(0)
            if isinstance(response, Exception):
                raise response
            return response
        return GeographyResolver(self.path / 'cache.json', fetcher=fetch, clock=lambda: self.at, rate_interval=0, rate_path=self.path / 'rate', **kwargs)

    def row(self, **address):
        return {'osm_type': 'relation', 'osm_id': 123, 'addresstype': 'village', 'lat': '49.1', 'lon': '24.1', 'address': {'country_code': 'ua', 'ISO3166-2-lvl4': 'UA-46', 'village': 'Зразкове', 'municipality': 'Зразкова сільська територіальна громада', **address}}

    def test_explicit_community_requires_provenance_and_makes_no_network_request(self):
        r = self.resolver([])
        result = r.resolve({**self.query, 'sourceCommunity': 'Справжня громада', 'sourceUrl': 'https://example.org/official/list'})
        self.assertEqual(result['community'], 'Справжня громада')
        self.assertEqual(result['method'], 'explicit-source-field')
        self.assertEqual(r.resolve({**self.query, 'sourceCommunity': 'Непідтверджена'})['status'], 'unresolved')
        self.assertEqual(self.calls, [])

    def test_exact_region_country_locality_and_preserved_cache_observation(self):
        r = self.resolver([[self.row()]])
        first = r.resolve(self.query)
        self.assertEqual(first['status'], 'resolved')
        self.assertEqual(first['community'], self.row()['address']['municipality'])
        self.at += 100
        self.assertEqual(r.resolve(self.query)['checkedAt'], first['checkedAt'])
        self.assertEqual(len(self.calls), 1)
        self.assertNotIn('house', urllib.parse.parse_qs(urllib.parse.urlsplit(self.calls[0]).query))

    def test_wrong_country_region_or_locality_never_produces_a_community(self):
        for address in [{'country_code': 'pl'}, {'ISO3166-2-lvl4': 'UA-05'}, {'village': 'Інше'}, {'village': 'Інше', 'city': 'Зразкове'}]:
            with self.subTest(address=address):
                r = self.resolver([[self.row(**address)]])
                self.assertEqual(r.resolve(self.query)['status'], 'unresolved')
                (self.path / 'cache.json').unlink(missing_ok=True)

    def test_same_name_distinct_places_are_ambiguous(self):
        second = self.row(); second['osm_id'] = 124
        r = self.resolver([[self.row(), second]])
        self.assertEqual(r.resolve(self.query)['reason'], 'ambiguous_locality')

    def test_missing_municipality_is_not_inferred_from_settlement_or_county(self):
        row = self.row(municipality=None, county='Зразковий район')
        r = self.resolver([[row], row])
        result = r.resolve(self.query)
        self.assertEqual(result['status'], 'unresolved')
        self.assertEqual(result['reason'], 'community_not_published')
        self.assertEqual(len(self.calls), 2)

    def test_search_can_use_reverse_metadata_but_reverse_must_match_the_same_locality(self):
        r = self.resolver([[self.row(municipality=None)], self.row()])
        self.assertEqual(r.resolve(self.query)['status'], 'resolved')
        (self.path / 'cache.json').unlink()
        r = self.resolver([[self.row(municipality=None)], self.row(village='Інше')])
        self.assertEqual(r.resolve(self.query)['status'], 'unresolved')

    def test_coordinates_use_reverse_and_do_not_share_a_wrong_name_only_cache(self):
        r = self.resolver([[], self.row()])
        self.assertEqual(r.resolve(self.query)['status'], 'unresolved')
        self.assertEqual(r.resolve({**self.query, 'coordinates': {'latitude': 49.1, 'longitude': 24.1}})['status'], 'resolved')
        self.assertIn('/reverse?', self.calls[-1])
        self.assertEqual(r.resolve({**self.query, 'coordinates': {'latitude': float('nan'), 'longitude': 24}})['reason'], 'invalid_coordinates')

    def test_rate_state_is_shared_across_resolver_instances_and_cache_paths(self):
        times = []
        def fetch(url):
            times.append(self.at)
            return [self.row()]
        def sleep(delay):
            self.at += delay
        options = {'fetcher': fetch, 'clock': lambda: self.at, 'sleep': sleep, 'rate_path': self.path / 'shared-rate'}
        GeographyResolver(self.path / 'a.json', **options).resolve(self.query)
        GeographyResolver(self.path / 'b.json', **options).resolve(self.query)
        self.assertGreaterEqual(times[1] - times[0], 1.0)

    def test_transport_failure_is_explicit_and_cached_briefly(self):
        r = self.resolver([OSError('network'), [self.row()]])
        self.assertEqual(r.resolve(self.query)['reason'], 'source_unavailable')
        self.assertEqual(r.resolve(self.query)['status'], 'unresolved')
        self.at += 301
        self.assertEqual(r.resolve(self.query)['status'], 'resolved')

    def test_historical_client_region_matches_published_iso_only(self):
        row={'address':{'country_code':'ua','city':'Зразок','ISO3166-2-lvl4':'UA-77'}}
        self.assertTrue(GeographyResolver._matches(row,'Зразок','UA-73'))
        self.assertFalse(GeographyResolver._matches(row,'Зразок','UA-05'))
        self.assertFalse(GeographyResolver._matches(row,'Інший','UA-73'))

    def test_node_inside_same_named_boundary_with_same_community_is_one_place(self):
        relation=self.row();relation.update(osm_type='relation',lat='49',lon='24',boundingbox=['48.9','49.1','23.9','24.1'])
        node=self.row();node.update(osm_type='node',osm_id=456,lat='49.001',lon='24.001')
        self.assertTrue(GeographyResolver._same_node_boundary([node,relation]))
        node['lat']='49.05';self.assertFalse(GeographyResolver._same_node_boundary([node,relation]))
        node['lat']='49.001';node['address']={**node['address'],'municipality':'Інша'};self.assertFalse(GeographyResolver._same_node_boundary([node,relation]))

if __name__ == '__main__':
    unittest.main()
