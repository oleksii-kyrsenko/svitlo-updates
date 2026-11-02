"""Fail-closed release gate for independent capital-address UI coverage.

This checks retained artifacts, identity, independent original-source review and
consecutive time coverage. A successful CI job alone never counts as coverage.
JSON schema/examples are documented in README.md beside this file.
"""
import argparse
import collections
import html
import json
import pathlib
import re
import xml.etree.ElementTree as ET
from urllib.parse import unquote, urlparse

from common import (address_identity, checked_artifact, digest, normal, read_json,
                    street_identity, timestamp, write_json)


def require(value, message):
    if not value:
        raise ValueError(message)


def same_address(case, result):
    require(address_identity(result) == address_identity(case), 'result changed frozen geographic identity')


def verify_selected_address(case, result):
    def street_key(value):
        kind, name = street_identity(value)
        return kind, tuple(sorted(name.split()))
    names = [case['exactStreet'], *case.get('confirmedStreetVariants', []), *case.get('reviewedDisplayStreetVariants', [])]
    selected = str(result.get('selectedStreetLabel', '')).split(' · ')[0]
    require(street_key(selected) in {street_key(n) for n in names}, 'UI selected a different street/type')
    require(normal(result.get('selectedHouse', '')) == normal(case['exactHouse']), 'UI selected a different house/letter/corpus')
    label = str(result.get('selectedCityLabel', '')).split(' · ')[0]
    city_name = re.sub(r'^(?:м\.?|місто|с\.?|село|с-ще|селище|смт\.?)\s+', '', normal(label))
    require(city_name == normal(case['city']), 'UI selected another settlement')
    parts = result['persistedPlace'].get('addressParts') or {}
    require(normal(parts.get('settlement', '')) == normal(case['city']), 'saved settlement differs from target')
    require(street_key(parts.get('street', '')) in {street_key(n) for n in names}, 'saved street differs from target')
    require(normal(parts.get('house', '')) == normal(case['exactHouse']), 'saved house differs from target')


def approved_source(url, authority, review, roots):
    """A shared document host needs a retained, resource-specific official link."""
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.fragment or any(
            part in ('.', '..') for part in unquote(parsed.path).split('/')):
        return False
    # Sets remain supported for callers that supply a simple operator host list.
    if not isinstance(authority, dict):
        return parsed.hostname in authority
    if parsed.hostname in authority.get('approvedHosts', []):
        return True
    for rule in authority.get('linkedResources', []):
        prefix = rule.get('urlPrefix', '')
        if not prefix.endswith('/') or not url.startswith(prefix):
            continue
        proof = review.get('authorityLink', {})
        if proof.get('sourceUrl') != rule.get('authorityUrl'):
            continue
        authority_url = urlparse(proof['sourceUrl'])
        if authority_url.scheme != 'https' or authority_url.hostname not in authority.get('approvedHosts', []):
            continue
        original = checked_artifact(roots, proof['original'])
        if digest(original) != rule.get('authoritySha256'):
            continue
        body = original.decode('utf-8', errors='replace')
        links = [html.unescape(m) for m in re.findall(r'href=["\']([^"\']+)', body, re.I)]
        if any(link.startswith(prefix) for link in links):
            return True
    return False


def check_original_review(case, row, queue, scope, roots, sources, event_time):
    review = row['officialReview']
    require(review.get('method') == 'independent-original-source', 'independent original-source review missing')
    require(review.get('reviewer') and review.get('reviewer') != row['ui'].get('producer'), 'reviewer must differ from UI producer')
    require(review.get('addressFingerprint') == address_identity(case), 'official review identifies another address')
    require(str(review.get('queue')) == str(queue) and review.get('scope') == scope, 'source review disagrees with queue/scope')
    require(review.get('provenance') == 'official' and review.get('unambiguous') is True, 'unconfirmed/probable source result')
    require(review.get('operatorId') == row['operatorId'], 'source review identifies another operator')
    parsed = urlparse(review['sourceUrl'])
    require(parsed.scheme == 'https' and not parsed.username and not parsed.password, 'invalid source URL')
    approved = sources.get(row['operatorId'], set())
    require(approved_source(review['sourceUrl'], approved, review, roots),
            'official source host/resource has not been approved for this operator')
    observed, expires = timestamp(review['observedAt']), timestamp(review['expiresAt'])
    require(observed <= event_time < expires, 'official evidence was unavailable/expired at the UI result')
    require((expires - observed).total_seconds() <= 24 * 3600, 'official evidence TTL exceeds the supported 24h ceiling')
    original = checked_artifact(roots, review['original'])
    text = original
    if 'extractedText' in review:
        require(review.get('extractedFromSha256') == digest(original), 'extracted text is not linked to the original source')
        text = checked_artifact(roots, review['extractedText'])
    excerpt = review.get('excerpt', '')
    require(len(excerpt.strip()) >= 5 and excerpt.encode() in text, 'supporting source excerpt absent from retained original/text')
    require(review.get('addressMatched') is True and review.get('queueMatched') is True, 'source review did not verify both address and queue')
    if scope != 'house':
        require(review.get('explicitWholeScope') is True and review.get('boundariesAndExclusionsChecked') is True,
                'territorial result lacks explicit complete scope/boundary verification')
    require(scope in ('house', 'street', 'settlement', 'territory'), 'unsupported official coverage scope')
    return review


def check_attempts(row, roots):
    attempts = row.get('attempts', [])
    require(attempts, 'attempt chain missing')
    included = []
    for attempt in attempts:
        checked_artifact(roots, attempt['result'])
        if attempt.get('disposition') == 'included':
            included.append(attempt)
        elif attempt.get('disposition') == 'technical-invalid':
            require(attempt.get('technicalExplanation') and attempt.get('reviewer'), 'technical retry requires explanation and reviewer')
            checked_artifact(roots, attempt['diagnostic'])
            require(attempt.get('reason') in ('automation-input', 'automation-navigation', 'emulator-system-failure'),
                    'ordinary source failures may not be discarded as technical retries')
        else:
            raise ValueError('unknown attempt disposition')
    require(len(included) == 1, 'exactly one substantive attempt is permitted per case/cycle')
    require(included[0]['result'] == row['ui']['result'], 'counted result is not the substantive attempt')


def check_result(case, row, roots, cycle, sources):
    require(row.get('addressFingerprint') == address_identity(case), 'row changed frozen geographic identity')
    require(row.get('operatorId'), 'operator identity missing')
    check_attempts(row, roots)
    ui = row['ui']
    require(ui.get('producer'), 'UI evidence producer missing')
    result = json.loads(checked_artifact(roots, ui['result']))
    require(result.get('id') == case['id'], 'UI result belongs to another case')
    same_address(case, result)
    require(result.get('method') in ('released-apk-visible-ui', 'signed-apk-visible-ui'), 'result was not obtained through actual APK UI')
    require(result.get('apkCode') == cycle['apk']['versionCode'], 'result uses a different APK version')
    require(result.get('apkSha256') == cycle['apk']['sha256'], 'result uses a different or unidentified APK hash')
    require(result.get('androidApi') == cycle['androidApi'], 'result uses a different Android API')
    start, finish = timestamp(result['startedAt']), timestamp(result['finishedAt'])
    require(timestamp(cycle['startedAt']) <= start <= finish <= timestamp(cycle['completedAt']), 'UI result lies outside this cycle')
    require(not result.get('queueEnteredManually') and not result.get('addressStorageSeeded'), 'manual queue/storage seeding is forbidden')
    screenshot = checked_artifact(roots, ui['screenshot'])
    require(screenshot.startswith(b'\x89PNG\r\n\x1a\n'), 'real Android screenshot missing')
    xml = ET.fromstring(checked_artifact(roots, ui['queueTree']))
    place = result.get('persistedPlace') or {}
    if result.get('outcome') != 'queue_found_official':
        return False, result.get('outcome') or 'unresolved', result
    require(result.get('addressSelectedThroughUI') is True and result.get('saved') is True and not result.get('uiIssues'),
            'official result has unresolved UI/address-selection issues')
    verify_selected_address(case, result)
    require(place.get('operatorId') == row['operatorId'], 'saved operator differs from reviewed source')
    require(place.get('queueOrigin') == 'official' and place.get('queueConfirmed') is True, 'saved result is not a confirmed official queue')
    queue, scope = str(place.get('queue', '')), place.get('queueScope')
    require(re.fullmatch(r'[1-9]\d?(?:\.\d{1,2})?', queue) and str(result.get('visibleQueue')) == queue,
            'visible queue differs from saved queue or is not a valid queue')
    labels = [n.get(k, '') for n in xml.iter() for k in ('text', 'content-desc')]
    queue_pattern = re.compile(r'(?<![\d.])' + re.escape(queue) + r'(?![\d.])')
    require(any('черга' in normal(label) and queue_pattern.search(label) for label in labels), 'queue not present in its actual accessibility tree')
    check_original_review(case, row, queue, scope, roots, sources, finish)
    return True, 'official', result


def check_regressions(cycle, baseline, roots):
    expected = {c['id']: c for c in baseline['cases'] if c.get('baseline', {}).get('category') == 'official_house'}
    rows = cycle.get('sameResponseRegressions', [])
    require(len(rows) == 38 and {r.get('caseId') for r in rows} == set(expected), 'all38 original successes require identical-response regression evidence')
    for row in rows:
        case = expected[row['caseId']]
        require(row.get('addressFingerprint') == address_identity(case), 'regression changed frozen address')
        snapshot = checked_artifact(roots, row['sourceSnapshot'])
        before = json.loads(checked_artifact(roots, row['before']))
        after = json.loads(checked_artifact(roots, row['after']))
        for result in (before, after):
            require(result.get('sourceSnapshotSha256') == digest(snapshot), 'regression inputs are not identical source snapshots')
            require(result.get('caseId') == case['id'] and result.get('addressFingerprint') == address_identity(case), 'regression result identifies another address')
            require(result.get('queue') == case['baseline']['queue'] and result.get('provenance') == 'official', 'original successful queue regressed')
        require(before.get('runtimeCommit') == baseline['originRuntimeCommit'] and after.get('runtimeCommit') == cycle['runtimeCommit'],
                'same-response comparison does not identify original and candidate runtimes')


def validate_samples(baseline, holdout, protocol, baseline_bytes, holdout_bytes=None):
    require(digest(baseline_bytes) == protocol['baselineSampleSha256'], 'baseline file differs from the frozen protocol')
    require(len(baseline['cases']) == 110, 'baseline must contain110 cases')
    require(holdout.get('kind') == 'capital-holdout' and holdout.get('status') == 'frozen' and holdout.get('coverageInputsUsed') is False,
            'independent holdout has not been frozen')
    require(holdout.get('baselineSha256') == protocol['baselineSampleSha256'], 'holdout was built against a different baseline')
    require(protocol.get('holdoutStatus') == 'frozen' and holdout_bytes is not None and
            digest(holdout_bytes) == protocol.get('holdoutSampleSha256'),
            'holdout has not been independently frozen and pinned in the protocol')
    require(len(holdout['cases']) == 440, 'holdout must contain440 cases')
    excluded = set(protocol['excludedTestRegionIds'])
    baseline_regions = {c['regionId'] for c in baseline['cases']}
    require(len(baseline_regions) == 22 and not baseline_regions & excluded, 'test regions changed')
    counts = collections.Counter(c['regionId'] for c in holdout['cases'])
    require(set(counts) == baseline_regions and set(counts.values()) == {20}, 'holdout requires20 cases in each original city')
    original_objects = {(c['osmType'], c['osmId']) for c in baseline['cases']}
    ids = set()
    identities = set()
    for case in baseline['cases'] + holdout['cases']:
        identity = address_identity(case)
        require(case['id'] not in ids and identity not in identities, 'duplicate case/address in samples')
        ids.add(case['id']); identities.add(identity)
    for case in holdout['cases']:
        require((case['osmType'], case['osmId']) not in original_objects, 'holdout reuses an original building')
        require(case.get('selectedWithoutQueueData') is True and case.get('verification'), 'holdout lacks geographic selection evidence')
    return baseline_regions


def evaluate(baseline_path, holdout_path, cycle_paths, artifacts, protocol_path=None, sources_path=None):
    here = pathlib.Path(__file__).parent
    protocol = read_json(protocol_path or here/'protocol.json')
    baseline_bytes = pathlib.Path(baseline_path).read_bytes()
    holdout_bytes = pathlib.Path(holdout_path).read_bytes()
    baseline, holdout = json.loads(baseline_bytes), json.loads(holdout_bytes)
    validate_samples(baseline, holdout, protocol, baseline_bytes, holdout_bytes)
    variants = read_json(here/'reviewed-display-variants.json')['variants']
    for case in baseline['cases']:
        case['reviewedDisplayStreetVariants'] = variants.get(case['id'], [])
    authority = read_json(sources_path or here/'source-authorities.json')
    sources = {r['operatorId']: r for r in authority['operators']}
    samples = {'baseline': baseline['cases'], 'holdout': holdout['cases']}
    hashes = {'baseline': digest(baseline_bytes), 'holdout': digest(pathlib.Path(holdout_path).read_bytes())}
    cycles, seen_ids = [], set()
    previous_hash = None
    for path in cycle_paths:
        cycle = read_json(path)
        errors, report = [], {'cycleId': cycle.get('cycleId'), 'sets': {}, 'remainingFailures': []}
        try:
            require(cycle.get('schemaVersion') == 1 and cycle.get('cycleId') and cycle['cycleId'] not in seen_ids, 'invalid/duplicate cycle identity')
            seen_ids.add(cycle['cycleId'])
            require(cycle.get('sequence') == len(cycles) + 1 and cycle.get('previousCycleSha256') == previous_hash,
                    'cycle history must be complete and hash-linked from sequence1')
            require(cycle.get('noAddressStorageSeeding') is True and cycle.get('noManualQueueInputs') is True, 'cycle must prohibit address/queue seeding')
            require(re.fullmatch(r'[a-f0-9]{64}', cycle['apk']['sha256']) and isinstance(cycle['apk']['versionCode'], int), 'APK identity missing')
            apk_bytes = checked_artifact(artifacts, cycle['apk']['artifact'])
            require(digest(apk_bytes) == cycle['apk']['sha256'] and apk_bytes.startswith(b'PK\x03\x04'),
                    'retained APK differs from the tested APK identity')
            require(re.fullmatch(r'[a-f0-9]{40}', cycle.get('runtimeCommit', '')), 'candidate runtime identity missing')
            require(cycle.get('androidApi') in (30, 35, 36), 'unsupported Android acceptance API')
            require(timestamp(cycle['startedAt']) < timestamp(cycle['completedAt']), 'invalid cycle interval')
            require(cycle.get('sampleSha256') == hashes, 'cycle did not use the exact frozen samples')
            for name, cases in samples.items():
                rows = cycle.get('sets', {}).get(name, [])
                require(len(rows) == len(cases) and {r.get('caseId') for r in rows} == {c['id'] for c in cases}, 'missing/duplicate/extra cases in ' + name)
                indexed = {r['caseId']: r for r in rows}
                successes, by_city = 0, {}
                for case in cases:
                    city = by_city.setdefault(case['city'], {'official': 0, 'total': 0, 'goal': 100})
                    city['total'] += 1
                    try:
                        official, cause, result = check_result(case, indexed[case['id']], artifacts, cycle, sources)
                    except (ValueError, KeyError, TypeError, json.JSONDecodeError, ET.ParseError) as error:
                        official, cause = False, 'invalid-evidence: ' + str(error)
                    if official:
                        successes += 1; city['official'] += 1
                    else:
                        report['remainingFailures'].append({'sample': name, 'caseId': case['id'], 'city': case['city'], 'cause': cause})
                minimum = protocol[name + 'MinimumOfficial']
                report['sets'][name] = {'official': successes, 'total': len(cases), 'minimum': minimum,
                                       'minimumMet': successes >= minimum, 'byCity': by_city}
            check_regressions(cycle, baseline, artifacts)
            if not all(s['minimumMet'] for s in report['sets'].values()):
                errors.append('one or both independent sample minimums not met')
        except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError) as error:
            errors.append(str(error))
        report.update({'errors': errors, 'passed': not errors, 'startedAt': cycle.get('startedAt'),
                       'completedAt': cycle.get('completedAt'), 'apk': cycle.get('apk'), 'input': str(path)})
        cycles.append(report)
        previous_hash = digest(pathlib.Path(path).read_bytes())
    require(len(cycles) >= 3, 'at least3 consecutive complete cycles are required')
    require(all(timestamp(a['completedAt']) <= timestamp(b['startedAt']) for a, b in zip(cycles, cycles[1:])),
            'cycle history must be chronological and non-overlapping; include intervening failures')
    latest = cycles[-3:]
    apk_identity = lambda c: ((c.get('apk') or {}).get('sha256'), (c.get('apk') or {}).get('versionCode'))
    same_apk = all(apk_identity(c) == apk_identity(latest[0]) for c in latest)
    duration = (timestamp(latest[-1]['completedAt']) - timestamp(latest[0]['startedAt'])).total_seconds() / 3600
    passed = all(c['passed'] for c in latest) and same_apk and duration >= 24
    return {'schemaVersion': 1, 'passed': passed, 'minimumPercent': 90, 'goalPercent': 100,
            'cycles': cycles, 'consecutiveSameApk': same_apk, 'observationHours': round(duration, 3),
            'remainingFailures': latest[-1]['remainingFailures'],
            'limits': ['Sample coverage is not proof of all city addresses.',
                       'Native API30/35/36 screenshots, data-preserving upgrade and cache/revocation checks remain mandatory APK release gates.',
                       'All chronological cycle records must be retained; this verifier cannot discover an omitted remote run.']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', default=str(pathlib.Path(__file__).with_name('baseline.json')))
    parser.add_argument('--holdout', required=True)
    parser.add_argument('--cycles', required=True, nargs='+')
    parser.add_argument('--artifacts', required=True)
    parser.add_argument('--protocol')
    parser.add_argument('--sources')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        report = evaluate(args.baseline, args.holdout, args.cycles, args.artifacts, args.protocol, args.sources)
    except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError) as error:
        report = {'schemaVersion': 1, 'passed': False, 'errors': [str(error)]}
    write_json(args.output, report)
    print('Capital coverage acceptance: ' + ('PASS' if report['passed'] else 'FAIL'))
    raise SystemExit(0 if report['passed'] else 1)
