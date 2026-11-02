"""Freeze 20 independent geographic addresses per capital, without queue inputs.

Input is an OSM candidate envelope; every candidate has an original Nominatim
address verification artifact. This command does not fabricate unavailable
addresses or substitute another city. It refuses an incomplete 440-case sample.
"""
import argparse
import math
import pathlib
from urllib.parse import urlparse

from common import (address_identity, canonical, checked_artifact, digest, distance_km,
                    normal, read_json, street_identity, timestamp, write_json)


def region_from_city_reference(case, city, address, result):
    """A missing ISO field may use the original, verified city-boundary proof.

    An explicit contradictory ISO field is never overridden. Names alone do
    not establish the region: community and the source boundary's bounds must
    identify the same frozen settlement as well.
    """
    import json,hashlib
    root=pathlib.Path(__file__).resolve().parents[2]
    directory=read_json(root/'coverage/capital-geography.json')
    raw=(root/directory['sourceSnapshot']).read_bytes()
    if digest(raw)!=directory['sourceSnapshotSha256']:return False
    entries=[c for c in directory['cities'] if c['regionId']==case['regionId'] and normal(c['settlement'])==normal(city['city'])]
    if len(entries)!=1:return False
    entry=entries[0]
    records=[r for r in json.loads(raw)['records'] if r.get('osm_type')=='relation' and r.get('osm_id')==entry['osmRelation']]
    if len(records)!=1:return False
    reference=records[0];reference_address=reference.get('address',{})
    if hashlib.sha256(json.dumps(reference,sort_keys=True,ensure_ascii=False).encode()).hexdigest()!=entry['sourceRecordSha256']:return False
    codes={('UA-73' if v=='UA-77' else v) for k,v in reference_address.items() if k.startswith('ISO3166-2-')}
    if case['regionId'] not in codes or reference_address.get('country_code')!='ua':return False
    if not entry.get('community') or normal(address.get('municipality',''))!=normal(entry['community']):return False
    if normal(reference_address.get('city',''))!=normal(city['city']):return False
    south,north,west,east=map(float,reference['boundingbox'])
    return south<=float(result['lat'])<=north and west<=float(result['lon'])<=east


def validate_candidate(case, city, evidence):
    if case.get('selectedWithoutQueueData') is not True:
        raise ValueError('candidate provenance must explicitly exclude queue-source inputs')
    if case.get('regionId') != city['regionId'] or normal(case.get('city')) != normal(city['city']):
        raise ValueError('candidate has a different city/region')
    if case.get('osmType') not in ('node', 'way', 'relation') or not isinstance(case.get('osmId'), int):
        raise ValueError('candidate requires an original OSM identity')
    lat, lon = float(case['latitude']), float(case['longitude'])
    if not (44 <= lat <= 53 and 22 <= lon <= 41):
        raise ValueError('candidate coordinates outside Ukraine')
    verification = case['verification']
    if verification.get('method') != 'nominatim-address':
        raise ValueError('unsupported geographic verification method')
    parsed = urlparse(verification.get('sourceUrl', ''))
    if parsed.scheme != 'https' or parsed.hostname != 'nominatim.openstreetmap.org':
        raise ValueError('geographic verification must retain its original public Nominatim URL')
    timestamp(verification['checkedAt'])
    import json
    original = json.loads(checked_artifact(evidence, verification['artifact']))
    originals = original if isinstance(original, list) else [original]
    matching = [r for r in originals if r.get('osm_type') == case['osmType'] and int(r.get('osm_id', -1)) == case['osmId']]
    if len(matching) != 1:
        raise ValueError('verification does not identify this exact OSM building')
    result = matching[0]
    address = result.get('address', {})
    if address.get('country_code') != 'ua':
        raise ValueError('verification does not establish Ukraine membership')
    regions={('UA-73' if v=='UA-77' else v) for k,v in address.items() if k.startswith('ISO3166-2-')}
    if case['regionId'] not in regions and (regions or not region_from_city_reference(case,city,address,result)):
        raise ValueError('verification does not establish the requested region membership')
    if not any(normal(address.get(k, '')) == normal(city['city']) for k in ('city', 'town', 'village')):
        raise ValueError('verification does not establish the requested city membership')
    if normal(address.get('house_number', '')) != normal(case['exactHouse']):
        raise ValueError('verification does not identify the exact house number')
    if not any(street_identity(address.get(k, '')) == street_identity(case['exactStreet'])
               for k in ('road', 'pedestrian', 'residential')):
        raise ValueError('verification does not identify the exact street/type')
    if distance_km(case, {'latitude': result['lat'], 'longitude': result['lon']}) > 0.12:
        raise ValueError('verification location differs from the frozen building')
    address_identity(case)


def quadrant(point, city):
    return (point['latitude'] >= city['centerLatitude']) * 2 + (point['longitude'] >= city['centerLongitude'])


def choose_city(city, candidates, baseline, evidence):
    existing_objects = {(c['osmType'], c['osmId']) for c in baseline}
    existing_addresses = {(street_identity(c['exactStreet']), normal(c['exactHouse'])) for c in baseline}
    valid, rejected = {}, []
    for candidate in candidates:
        try:
            validate_candidate(candidate, city, evidence)
            object_key = (candidate['osmType'], candidate['osmId'])
            if object_key in existing_objects or (street_identity(candidate['exactStreet']), normal(candidate['exactHouse'])) in existing_addresses:
                continue
            identity = address_identity(candidate)
            if object_key in valid and address_identity(valid[object_key]) != identity:
                raise ValueError('conflicting addresses for the same OSM object')
            valid[object_key] = candidate
        except (ValueError, KeyError, TypeError) as error:
            rejected.append({'osmId': candidate.get('osmId'), 'reason': str(error)})
    center = {'latitude': city['centerLatitude'], 'longitude': city['centerLongitude']}
    ranked = sorted(valid.values(), key=lambda c: (distance_km(c, center), digest(canonical(c))))
    if not ranked:
        return [], rejected
    # Geography only: the city extent fixes zone boundaries before any lookup.
    extent = max(distance_km(c, center) for c in ranked)
    center_radius = max(0.75, min(2.0, extent * .25))
    # City boundaries are rarely circular. A long industrial/residential arm
    # in one direction must not define the outskirts in every other direction.
    quadrant_extents={q:max((distance_km(c,center) for c in ranked if quadrant(c,city)==q),default=0) for q in range(4)}
    periphery_cutoffs={q:max(1.5,d*.6) for q,d in quadrant_extents.items()}
    peripheral=[c for c in ranked if distance_km(c,center)>=periphery_cutoffs[quadrant(c,city)]]
    peripheral_streets={street_identity(c['exactStreet']) for c in peripheral}
    selected, street_keys = [], set()
    for zone, count, pool in (
        ('center', 8, [c for c in ranked if distance_km(c, center) <= center_radius]),
        ('periphery', 12, peripheral)):
        quadrants = set()
        for _ in range(count):
            options = [c for c in pool if street_identity(c['exactStreet']) not in street_keys and
                       all(distance_km(c, previous) >= .25 for previous in selected)]
            if not options:
                return [], rejected + [{'reason': f'{city["city"]}: insufficient independently verified {zone} addresses'}]
            def rank(candidate):
                spread = min((distance_km(candidate, p) for p in selected), default=0)
                return (zone == 'periphery' and quadrant(candidate, city) not in quadrants,
                        zone == 'center' and street_identity(candidate['exactStreet']) not in peripheral_streets,
                        spread, digest(canonical(candidate)))
            chosen = dict(max(options, key=rank))
            chosen['zone'] = zone
            chosen['distanceFromCenterKm'] = round(distance_km(chosen, center), 4)
            chosen['zoneBoundaryKm']=round(center_radius if zone=='center' else periphery_cutoffs[quadrant(chosen,city)],4)
            selected.append(chosen)
            street_keys.add(street_identity(chosen['exactStreet']))
            quadrants.add(quadrant(chosen, city))
        if zone == 'periphery' and len(quadrants) < 3:
            return [], rejected + [{'reason': f'{city["city"]}: peripheral addresses cover fewer than three quadrants'}]
    for index, case in enumerate(selected, 1):
        case.update({'id': city['regionId'] + '-holdout-' + str(index), 'preferredStreet': case['exactStreet'],
                     'preferredHouse': case['exactHouse'], 'regionQuery': city['regionQuery'],
                     'centerLatitude': city['centerLatitude'], 'centerLongitude': city['centerLongitude'],
                     'community': city.get('community', ''), 'cityOsmRelation': city['cityOsmRelation'],
                     'role': 'обласний центр'})
    return selected, rejected


def generate(candidates_path, baseline_path, evidence):
    source, baseline = read_json(candidates_path), read_json(baseline_path)
    if source.get('coverageInputsUsed') is not False or source.get('kind') != 'geographic-candidates':
        raise ValueError('candidate envelope must exclude queue/coverage inputs')
    groups = {}
    for case in baseline['cases']:
        groups.setdefault(case['regionId'], []).append(case)
    cities = source.get('cities', [])
    if len(cities) != 22 or {c['regionId'] for c in cities} != set(groups):
        raise ValueError('candidate envelope must contain exactly the 22 baseline cities')
    cases, reports = [], []
    for city in sorted(cities, key=lambda c: c['regionId']):
        frozen_city = groups[city['regionId']][0]
        for key in ('city', 'cityOsmRelation', 'centerLatitude', 'centerLongitude'):
            expected=frozen_city.get(key)
            if key=='cityOsmRelation' and expected is None:
                geography=read_json(pathlib.Path(__file__).resolve().parents[1]/'capital-geography.json')
                expected=next(c['osmRelation'] for c in geography['cities'] if c['regionId']==city['regionId'])
            if city.get(key) != expected:
                raise ValueError('candidate city metadata differs from the frozen baseline: ' + key)
        selected, rejected = choose_city(city, city.get('candidates', []), groups[city['regionId']], evidence)
        cases.extend(selected)
        reports.append({'city': city['city'], 'selected': len(selected), 'rejected': rejected})
    result = {'schemaVersion': 1, 'kind': 'capital-holdout', 'status': 'frozen' if len(cases) == 440 else 'incomplete',
              'method': 'Queue-independent verified OSM buildings: 8 center+12 periphery/city; 20 distinct streets; >=250m separation; >=3 peripheral quadrants; periphery >=max(1.5km,60%verifiedextent in its quadrant).',
              'baselineSha256': digest(pathlib.Path(baseline_path).read_bytes()),
              'geographicInputSha256': digest(pathlib.Path(candidates_path).read_bytes()),
              'capitalGeographyDirectorySha256':digest((pathlib.Path(__file__).resolve().parents[1]/'capital-geography.json').read_bytes()),
              'capitalGeographySnapshotSha256':read_json(pathlib.Path(__file__).resolve().parents[1]/'capital-geography.json')['sourceSnapshotSha256'],
              'coverageInputsUsed': False, 'cases': cases, 'selectionReport': reports,
              'attribution': '© OpenStreetMap contributors, ODbL. Original geographic verification artifacts retained.'}
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidates', required=True)
    parser.add_argument('--baseline', default=str(pathlib.Path(__file__).with_name('baseline.json')))
    parser.add_argument('--evidence-directory', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = generate(args.candidates, args.baseline, args.evidence_directory)
    write_json(args.output, result)
    print(f'{result["status"]}: {len(result["cases"])} / 440 geographically verified addresses')
    raise SystemExit(0 if result['status'] == 'frozen' else 1)
