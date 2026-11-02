"""Materialize seven bounded, free-batch roles from unresolved address cards.

This is task assignment and evidence validation, not a claim that seven paid or
always-running models exist. Research/extraction may use the existing local CPU
model. Adapter changes still require reviewed source changes and tests.
"""
import argparse
import collections
import pathlib
from datetime import datetime, timezone
from urllib.parse import urlparse

from common import checked_artifact, read_json, timestamp, write_json

ROLES = {
    'coordinator': 'Order work by unresolved city/address coverage, review accepted evidence, retain all remaining failures toward100%.',
    'official-researcher-1': 'Investigate protected sources and find independently verifiable official alternatives.',
    'official-researcher-2': 'Investigate unavailable/unintegrated official sources and document address-to-queue protocols.',
    'address-specialist': 'Resolve geographic identity and address-selection failures without changing frozen targets.',
    'adapter-engineer': 'Implement/review collectors and matching fixes; verify same-response regressions.',
    'monitoring-specialist': 'Probe actual address endpoints and TTL/revocation; report source failures without renewing old observations.',
    'independent-verifier': 'Review original evidence independently from its producer; check boundaries and holdout results.'}


def checked_reports(reports, artifacts, ids):
    accepted, rejected = [], []
    seen = set()
    for report in reports:
        try:
            if report.get('reportId') in seen or not report.get('reportId'):
                raise ValueError('missing/duplicate report identity')
            seen.add(report['reportId'])
            if report.get('role') not in ROLES or report.get('caseId') not in ids:
                raise ValueError('unknown role or frozen failure case')
            if report.get('status') not in ('source-verified', 'adapter-verified', 'resolved-official', 'blocked-with-evidence'):
                raise ValueError('link counts and unverified guesses are not completion statuses')
            timestamp(report['observedAt'])
            if not report.get('findings') or not report.get('nextStep'):
                raise ValueError('finding and next step required, including for blockers')
            if not report.get('producer') or report.get('reviewerRole') != 'independent-verifier' or report.get('reviewer') == report.get('producer') or not report.get('reviewer'):
                raise ValueError('independent verification required')
            if not report.get('artifacts'):
                raise ValueError('original retained evidence required')
            for artifact in report['artifacts']:
                checked_artifact(artifacts, artifact)
            source = urlparse(report.get('sourceUrl', ''))
            if source.scheme != 'https' or not source.hostname:
                raise ValueError('original public official source URL required')
            if report['status'] == 'resolved-official' and not report.get('acceptanceCaseEvidence'):
                raise ValueError('resolution requires actual UI+independent source acceptance-case evidence')
            if report.get('acceptanceCaseEvidence'):
                checked_artifact(artifacts, report['acceptanceCaseEvidence'])
            accepted.append(report)
        except (ValueError, KeyError, TypeError, OSError) as error:
            rejected.append({'reportId': report.get('reportId'), 'caseId': report.get('caseId'), 'reason': str(error)})
    return accepted, rejected


def build_queue(backlog, reports, artifacts, per_role=12, state=None, baseline=None, now=None):
    cards = backlog['cards']
    ids = {c['id'] for c in cards}
    if len(ids) != len(cards) or not 1 <= per_role <= 72:
        raise ValueError('invalid backlog or per-role batch size')
    if state is not None and (state.get('schemaVersion') != 1 or not isinstance(state.get('cursors', {}), dict)):
        raise ValueError('invalid scheduler state')
    state = state if state is not None else {'schemaVersion': 1, 'cursors': {}, 'ledger': {}}
    cursors = state.setdefault('cursors', {})
    ledger = state.setdefault('ledger', {})
    if not isinstance(ledger, dict):
        raise ValueError('invalid dispatch ledger')
    observed = now or datetime.now(timezone.utc).isoformat()
    timestamp(observed)
    accepted, rejected = checked_reports(reports, artifacts, ids)
    histories = collections.defaultdict(list)
    for report in accepted:
        histories[report['caseId']].append(report)
    # A report never mutates the immutable baseline/backlog or proves a release
    # threshold. Only the acceptance gate can count a resolved official address.
    pools = {role: [] for role in ROLES}
    by_city = collections.defaultdict(list)
    for card in cards:
        if card['ownerRole'] not in ROLES:
            raise ValueError('unknown backlog role')
        by_city[card['city']].append(card)
    ordered = []
    for index in range(max(map(len, by_city.values()), default=0)):
        for city in sorted(by_city, key=lambda k: (-len(by_city[k]), k)):
            if index < len(by_city[city]):
                ordered.append(by_city[city][index])
    for card in ordered:
        history = sorted(histories[card['id']], key=lambda r: timestamp(r['observedAt']))
        task = {'taskId': 'case:' + card['id'], 'caseId': card['id'], 'city': card['city'], 'operatorId': card['operatorId'],
                'initialCause': card['initialCategory'], 'nextStep': history[-1]['nextStep'] if history else card['nextStep'],
                'lastVerifiedStatus': history[-1]['status'] if history else 'open',
                'evidenceReportIds': [r['reportId'] for r in history]}
        pools[card['ownerRole']].append(task)
        # The verifier also audits open failures: a missing report must not leave
        # that role permanently idle. A claimed resolution stays in the audit
        # queue and does not close this independently frozen failure card.
        pools['independent-verifier'].append(task)
    if baseline is None:
        baseline = read_json(pathlib.Path(__file__).with_name('baseline.json'))
    city_cases = collections.defaultdict(list)
    for case in baseline['cases']:
        city_cases[(case['regionId'], case['city'])].append(case)
    for (region, city), cases in sorted(city_cases.items()):
        failures = by_city.get(city, [])
        operator = next((c.get('operatorId') for c in failures if c.get('operatorId')), None)
        operator = operator or next((c.get('baseline', {}).get('operatorId') for c in cases
                                    if c.get('baseline', {}).get('operatorId')), None)
        monitor = {'taskId': 'city:' + region + ':' + city, 'city': city, 'regionId': region,
                   'operatorId': operator, 'caseIds': [c['id'] for c in cases],
                   'unresolvedCaseIds': [c['id'] for c in failures],
                   'nextStep': 'Verify actual address endpoints, provenance, TTL/revocation and complete-city crawl; homepage200 is insufficient.'}
        pools['monitoring-specialist'].append(monitor)
        pools['coordinator'].append({**monitor, 'nextStep': 'Review every city including prior successes, retain remaining failures toward100%, and verify independent acceptance gates.'})
    queues = {}
    active_ledger_keys = set()
    for role, tasks in pools.items():
        for task in tasks:
            active_ledger_keys.add(role + '/' + task['taskId'])
        cursor = cursors.get(role, 0)
        if not isinstance(cursor, int) or cursor < 0:
            raise ValueError('invalid role cursor')
        if not tasks:
            queues[role] = []
            cursors[role] = 0
            continue
        start = cursor % len(tasks)
        selected = [tasks[(start + index) % len(tasks)] for index in range(min(per_role, len(tasks)))]
        queues[role] = selected
        cursors[role] = (start + len(selected)) % len(tasks)
        for task in selected:
            key = role + '/' + task['taskId']
            prior = ledger.get(key, {})
            ledger[key] = {'dispatches': int(prior.get('dispatches', 0)) + 1,
                           'firstDispatchedAt': prior.get('firstDispatchedAt', observed),
                           'lastDispatchedAt': observed}
    # Only current task identities remain; an unbounded append-only log would
    # grow forever. Artifact/run history remains in CI, not in this state file.
    state['ledger'] = {key: value for key, value in ledger.items() if key in active_ledger_keys}
    state['updatedAt'] = observed
    return {'schemaVersion': 1, 'roles': ROLES, 'scheduler': 'bounded GitHub Actions batch; existing free CPU model optional; no paid persistent server',
            'goalPercent': 100, 'minimumPercent': 90, 'baselineFailureCount': len(cards), 'perRoleBatchLimit': per_role,
            'queues': queues, 'state': state, 'poolSizes': {role: len(tasks) for role, tasks in pools.items()},
            'acceptedReports': len(accepted), 'rejectedReports': rejected,
            'verifiedStatusCounts': dict(collections.Counter(r['status'] for r in accepted)),
            'releaseCoverage': 'Not inferred from task dispatch or agent reports. Use acceptance.py with real UI+independent official source evidence.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backlog', default=str(pathlib.Path(__file__).with_name('failures.json')))
    parser.add_argument('--reports', nargs='*', default=[])
    parser.add_argument('--artifacts', default='.')
    parser.add_argument('--per-role', type=int, default=12)
    parser.add_argument('--output', required=True)
    parser.add_argument('--state', help='Persist role cursors and bounded dispatch ledger between scheduled runs')
    parser.add_argument('--baseline', default=str(pathlib.Path(__file__).with_name('baseline.json')))
    args = parser.parse_args()
    reports = [read_json(path) for path in args.reports]
    state = read_json(args.state) if args.state and pathlib.Path(args.state).exists() else None
    queue = build_queue(read_json(args.backlog), reports, args.artifacts, args.per_role, state, read_json(args.baseline))
    write_json(args.output, queue)
    if args.state and not queue['rejectedReports']:
        target=pathlib.Path(args.state);target.parent.mkdir(parents=True, exist_ok=True)
        temporary=target.with_suffix(target.suffix+'.tmp');write_json(temporary, queue['state']);temporary.replace(target)
    print(f'Scheduled {sum(map(len, queue["queues"].values()))} bounded tasks; verified reports {queue["acceptedReports"]}; rejected {len(queue["rejectedReports"])}')
    raise SystemExit(1 if queue['rejectedReports'] else 0)
