"""Sourced community context, never inferred from a settlement's name.

CLI accepts one JSON object per line; Python callers use GeographyResolver.resolve.
Only settlement-level metadata is requested. No houses or subscriber identifiers.
"""
import argparse
import fcntl
import json
import math
import os
import re
import tempfile
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

BASE = 'https://nominatim.openstreetmap.org/'
REGIONS = {'UA-' + code for code in ('05','07','12','14','18','21','23','26','30','32','35','44','46','48','51','53','56','59','61','63','65','68','71','73','74','43','40')}
USER_AGENT = 'KolySvitloGeography/1.0 (+https://github.com/oleksii-kyrsenko/svitlo-updates)'

def name_key(value):
    value = unicodedata.normalize('NFKC', str(value or '')).casefold()
    value = re.sub(r"[’'ʼ`\s]+", ' ', value).strip()
    return re.sub(r'^(?:м\.|с\.|смт\.?|місто\s+|село\s+|селище\s+)\s*', '', value)

def https(value):
    try:
        parsed = urllib.parse.urlsplit(value)
        return parsed.scheme == 'https' and bool(parsed.hostname) and not parsed.username and not parsed.password and not parsed.fragment
    except (TypeError, ValueError):
        return False

def fetch_json(url):
    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Accept': 'application/json'})
    with urllib.request.urlopen(request, timeout=20) as response:
        raw = response.read(1_000_001)
        if len(raw) > 1_000_000:
            raise ValueError('response_too_large')
        return json.loads(raw)

class GeographyResolver:
    def __init__(self, cache_path=None, *, fetcher=fetch_json, clock=time.time, sleep=time.sleep, rate_interval=1.05, rate_path=None):
        self.cache_path = Path(cache_path or os.environ.get('SVITLO_GEOGRAPHY_CACHE') or Path(tempfile.gettempdir()) / 'koly-svitlo-geography-cache.json')
        self.rate_path = Path(rate_path or Path(tempfile.gettempdir()) / 'koly-svitlo-nominatim-rate.json')
        self.fetcher, self.clock, self.sleep, self.rate_interval = fetcher, clock, sleep, max(1.0, rate_interval) if rate_interval else 0

    def _request(self, endpoint, params):
        url = BASE + endpoint + '?' + urllib.parse.urlencode(params)
        self.rate_path.parent.mkdir(parents=True, exist_ok=True)
        with open(str(self.rate_path) + '.lock', 'a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                previous = float(self.rate_path.read_text())
            except (OSError, ValueError):
                previous = 0
            delay = previous + self.rate_interval - self.clock()
            if delay > 0:
                self.sleep(min(delay, self.rate_interval))
            # Hold the process-shared lock through the request: no parallel calls.
            self.rate_path.write_text(str(self.clock()))
            return self.fetcher(url), url

    def _cache(self, key, value=None):
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(str(self.cache_path) + '.lock', 'a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                values = json.loads(self.cache_path.read_text())
                if not isinstance(values, dict):
                    values = {}
            except (OSError, ValueError):
                values = {}
            if value is None:
                found = values.get(key)
                return dict(found['result']) if isinstance(found, dict) and found.get('expiresAt', 0) > self.clock() else None
            ttl = 30 * 86400 if value['status'] == 'resolved' else 300 if value.get('reason') == 'source_unavailable' else 86400
            values = {k: v for k, v in values.items() if isinstance(v, dict) and v.get('expiresAt', 0) > self.clock()}
            values[key] = {'expiresAt': self.clock() + ttl, 'result': value}
            # Bound cache growth without renewing any observation timestamps.
            if len(values) > 10000:
                values = dict(sorted(values.items(), key=lambda item: item[1]['expiresAt'], reverse=True)[:10000])
            temporary = self.cache_path.with_name(self.cache_path.name + '.' + str(os.getpid()) + '.tmp')
            temporary.write_text(json.dumps(values, ensure_ascii=False))
            temporary.replace(self.cache_path)
            return dict(value)

    @staticmethod
    def _matches(record, settlement, region):
        address = record.get('address', {}) if isinstance(record, dict) else {}
        if not isinstance(address, dict) or str(address.get('country_code', '')).lower() != 'ua':
            return False
        # The app's historical Chernivtsi ID is UA-73 (KATOTTG); ISO uses UA-77.
        # Keep persisted app IDs stable while accepting the published ISO metadata.
        codes = {('UA-73' if value == 'UA-77' else value) for key, value in address.items() if key.startswith('ISO3166-2-')}
        if region not in codes:
            return False
        # Postal locality fields only; municipality/county is not a substitute.
        locality = next((address[field] for field in ('village', 'town', 'city', 'hamlet') if address.get(field)), None)
        return locality is not None and name_key(locality) == name_key(settlement)

    @staticmethod
    def _same_node_boundary(records):
        if len(records)!=2 or {r.get('osm_type') for r in records}!={'node','relation'}:return False
        relation=next(r for r in records if r.get('osm_type')=='relation');node=next(r for r in records if r.get('osm_type')=='node')
        a=relation.get('address',{}).get('municipality');b=node.get('address',{}).get('municipality')
        if not a or name_key(a)!=name_key(b):return False
        try:
            south,north,west,east=map(float,relation['boundingbox']);lat,lon=float(node['lat']),float(node['lon']);rlat,rlon=float(relation['lat']),float(relation['lon'])
            if not all(math.isfinite(n) for n in [south,north,west,east,lat,lon,rlat,rlon]):return False
            metres=111320*math.hypot(lat-rlat,(lon-rlon)*math.cos(math.radians(lat)))
            return south<=lat<=north and west<=lon<=east and metres<=500
        except (KeyError,ValueError,TypeError):return False

    @staticmethod
    def _city_region(record, settlement, region):
        """A published city-region is its own administrative context.

        This is deliberately narrower than a missing municipality: an ordinary
        city, town, county or a matching city name cannot establish this fact.
        Nominatim publishes the city-region boundary at rank8 with the ISO4
        code on that same relation (for example Kyiv). No community is coined.
        """
        if not GeographyResolver._matches(record, settlement, region):
            return False
        address = record.get('address', {})
        return (record.get('osm_type') == 'relation'
                and isinstance(record.get('osm_id'), int) and record['osm_id'] > 0
                and record.get('category') == 'boundary'
                and record.get('type') == 'administrative'
                and record.get('addresstype') == 'city'
                and record.get('place_rank') == 8
                and address.get('ISO3166-2-lvl4') == region
                and not any(address.get(k) for k in ('municipality', 'state', 'county', 'district')))

    @staticmethod
    def context_from_record(record, settlement, region, source_url, checked_at):
        """Extract only explicit source context; shared by snapshot tooling."""
        if not https(source_url) or not GeographyResolver._matches(record, settlement, region):
            return None
        address = record['address']
        city_region = GeographyResolver._city_region(record, settlement, region)
        community = address.get('municipality')
        if city_region:
            community = address['city']
        if not isinstance(community, str) or not community.strip():
            return None
        result = {'status': 'resolved', 'community': community.strip(),
                  'sourceUrl': source_url, 'checkedAt': checked_at,
                  'method': 'nominatim-city-region' if city_region else 'nominatim-municipality'}
        if (record.get('osm_type') in ('relation', 'node')
                and isinstance(record.get('osm_id'), int) and record['osm_id'] > 0
                and record.get('addresstype') in ('city', 'town', 'village', 'hamlet')):
            result['cityId'] = 'osm-' + record['osm_type'] + '-' + str(record['osm_id'])
        if city_region:
            result.update(communityKind='city-region', regionUnique=True)
        return result

    def resolve(self, query):
        if not isinstance(query, dict):
            return {'status': 'unresolved', 'reason': 'invalid_input'}
        settlement, region = query.get('settlement'), query.get('regionId')
        if not isinstance(settlement, str) or not settlement.strip() or len(settlement) > 250 or region not in REGIONS:
            return {'status': 'unresolved', 'reason': 'invalid_input'}
        community = query.get('sourceCommunity')
        if isinstance(community, str) and community.strip():
            if len(community) > 250 or not https(query.get('sourceUrl')):
                return {'status': 'unresolved', 'reason': 'source_provenance_required'}
            return {'status': 'resolved', 'community': community.strip(), 'sourceUrl': query['sourceUrl'], 'checkedAt': int(self.clock() * 1000), 'method': 'explicit-source-field'}
        coordinates = query.get('coordinates')
        if coordinates is not None:
            try:
                lat, lon = float(coordinates['latitude']), float(coordinates['longitude'])
                if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
                    raise ValueError('coordinates')
            except (TypeError, ValueError, KeyError):
                return {'status': 'unresolved', 'reason': 'invalid_coordinates'}
        # Coordinates distinguish same-name localities; unresolved name-only results
        # must not poison later coordinate-specific requests.
        key = json.dumps(['geo-v5', region, name_key(settlement), [lat, lon] if coordinates is not None else None], ensure_ascii=False)
        try:
            cached = self._cache(key)
            if cached is None:
                # Preserve still-live successful v4 observations with their
                # original timestamps; only negative v4 caches need reprobe.
                legacy_key = json.dumps(['geo-v4', region, name_key(settlement), [lat, lon] if coordinates is not None else None], ensure_ascii=False)
                legacy = self._cache(legacy_key)
                if (legacy and legacy.get('status') == 'resolved'
                        and isinstance(legacy.get('community'), str) and legacy['community'].strip()
                        and https(legacy.get('sourceUrl'))):
                    cached = legacy
        except OSError:
            cached = None
        if cached:
            return cached
        result = {'status': 'unresolved', 'reason': 'no_matching_locality'}
        try:
            params = {'format': 'jsonv2', 'addressdetails': 1, 'accept-language': 'uk'}
            if coordinates is not None:
                candidate, source_url = self._request('reverse', {**params, 'lat': lat, 'lon': lon, 'zoom': 12})
                candidates = [candidate] if self._matches(candidate, settlement, region) else []
            else:
                records, source_url = self._request('search', {**params, 'q': name_key(settlement) + ', Україна', 'countrycodes': 'ua', 'limit': 10})
                if not isinstance(records, list):
                    raise ValueError('invalid_response')
                candidates = [r for r in records if self._matches(r, settlement, region) and r.get('addresstype') in ('city', 'town', 'village', 'hamlet')]
                identities = {(r.get('osm_type'), r.get('osm_id')) for r in candidates}
                if len(identities) > 1 and self._same_node_boundary(candidates):
                    candidates = [next(r for r in candidates if r['osm_type']=='relation')]
                elif len(identities) > 1:
                    candidates = []
                    result['reason'] = 'ambiguous_locality'
            if len(candidates) == 1:
                candidate = candidates[0]
                community = candidate['address'].get('municipality')
                if (not community and not self._city_region(candidate, settlement, region)
                        and coordinates is None and candidate.get('lat') and candidate.get('lon')):
                    candidate, source_url = self._request('reverse', {**params, 'lat': candidate['lat'], 'lon': candidate['lon'], 'zoom': 12})
                    community = candidate.get('address', {}).get('municipality') if self._matches(candidate, settlement, region) else None
                context = self.context_from_record(candidate, settlement, region, source_url, int(self.clock() * 1000))
                if context:
                    result = context
                else:
                    result['reason'] = 'community_not_published'
            elif len(candidates) > 1:
                result['reason'] = 'ambiguous_locality'
            result.setdefault('sourceUrl', source_url)
            result.setdefault('checkedAt', int(self.clock() * 1000))
        except Exception:
            result = {'status': 'unresolved', 'reason': 'source_unavailable', 'checkedAt': int(self.clock() * 1000)}
        try:
            return self._cache(key, result)
        except OSError:
            return result

_default_resolver = None

def resolve(query, cache_path=None):
    """Convenience function for collectors; class instances allow explicit caches."""
    global _default_resolver
    if cache_path is not None:
        return GeographyResolver(cache_path).resolve(query)
    if _default_resolver is None:
        _default_resolver = GeographyResolver()
    return _default_resolver.resolve(query)

def main():
    import sys
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', help='Persistent cache JSON path')
    args = parser.parse_args()
    resolver = GeographyResolver(args.cache)
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            result = resolver.resolve(json.loads(line))
        except (ValueError, TypeError):
            result = {'status': 'unresolved', 'reason': 'invalid_input'}
        print(json.dumps(result, ensure_ascii=False), flush=True)

if __name__ == '__main__':
    main()
