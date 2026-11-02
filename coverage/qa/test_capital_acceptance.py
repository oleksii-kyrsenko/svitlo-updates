"""Synthetic evidence tests only; these fixtures are never coverage results."""
import base64
import collections
import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'capitals'))
from common import address_identity, canonical, digest, read_json, write_json
from acceptance import (approved_source, check_attempts, check_result, evaluate,
                        validate_samples, verify_selected_address)
from workqueue import build_queue

HERE = Path(__file__).resolve().parents[1] / 'capitals'
PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aYd0AAAAASUVORK5CYII=')


class EvidenceFixture:
    def __init__(self, root):
        self.root = Path(root)
        self.baseline = read_json(HERE / 'baseline.json')
        self.protocol = read_json(HERE / 'protocol.json')
        self.baseline_path = self.root / 'baseline.json'
        self.baseline_path.write_bytes((HERE / 'baseline.json').read_bytes())
        self.protocol_path = self.root / 'protocol.json'
        write_json(self.protocol_path, self.protocol)
        counts = collections.Counter()
        cases = []
        by_region = {c['regionId']: c for c in self.baseline['cases']}
        for region, base in sorted(by_region.items()):
            for i in range(20):
                case = copy.deepcopy(base)
                case.update(id=region + '-holdout-' + str(i+1), osmId=9000000000+len(cases),
                            exactStreet='вулиця Контрольна ' + str(i), exactHouse=str(i+100),
                            selectedWithoutQueueData=True, verification={'syntheticTestOnly': True})
                cases.append(case)
        self.holdout = {'kind':'capital-holdout', 'status':'frozen', 'coverageInputsUsed':False,
                        'baselineSha256':digest(self.baseline_path.read_bytes()), 'cases':cases}
        self.holdout_path = self.root / 'holdout.json'
        write_json(self.holdout_path, self.holdout)
        self.protocol.update(holdoutStatus='frozen',holdoutSampleSha256=digest(self.holdout_path.read_bytes()))
        write_json(self.protocol_path,self.protocol)
        self.apk = self.put(b'PK\x03\x04SYNTHETIC TEST APK', 'apk')
        self.sources_path = self.root / 'sources.json'
        self.operators = {c['regionId']:c['baseline']['operatorId'] for c in self.baseline['cases'] if c['baseline']['operatorId']}
        operators = set(self.operators.values())
        write_json(self.sources_path, {'operators':[{'operatorId':o, 'approvedHosts':['official.example']} for o in operators]})
        self.screenshot = self.put(PNG, 'png')
        self.snapshot = self.put(b'Synthetic unchanged official source snapshot for regression format tests', 'txt')
        self.cycles = []

    def put(self, value, extension='json'):
        raw = value if isinstance(value, bytes) else canonical(value)
        sha = digest(raw)
        path = sha + '.' + extension
        (self.root / path).write_bytes(raw)
        return {'path':path, 'sha256':sha}

    def make_row(self, case, start, official=True):
        queue = case.get('baseline', {}).get('queue') or '1.1'
        operator = case['baseline']['operatorId'] or self.operators[case['regionId']]
        outcome = 'queue_found_official' if official else 'source_protected'
        result = {**case, 'method':'signed-apk-visible-ui', 'apkCode':89, 'apkSha256':self.apk['sha256'],
                  'androidApi':35, 'startedAt':(start+timedelta(minutes=1)).isoformat(),
                  'finishedAt':(start+timedelta(minutes=2)).isoformat(), 'outcome':outcome,
                  'addressSelectedThroughUI':True, 'saved':True, 'uiIssues':[],
                  'selectedStreetLabel':case['exactStreet'], 'selectedHouse':case['exactHouse'],
                  'selectedCityLabel':'м. '+case['city'], 'visibleQueue':queue,
                  'persistedPlace':{'operatorId':operator, 'queue':queue, 'queueOrigin':'official',
                                    'queueConfirmed':True, 'queueScope':'house',
                                    'addressParts':{'settlement':case['city'], 'street':case['exactStreet'], 'house':case['exactHouse']}}}
        result_ref = self.put(result)
        tree = self.put(('<hierarchy><node text="Черга '+queue+'"/></hierarchy>').encode(), 'xml')
        excerpt = case['city']+', '+case['exactStreet']+', '+case['exactHouse']+' — черга '+queue
        original = self.put(excerpt.encode(), 'txt')
        review = {'method':'independent-original-source', 'reviewer':'fixture-reviewer',
                  'addressFingerprint':address_identity(case), 'queue':queue, 'scope':'house',
                  'provenance':'official', 'unambiguous':True, 'operatorId':operator,
                  'sourceUrl':'https://official.example/addresses', 'observedAt':start.isoformat(),
                  'expiresAt':(start+timedelta(hours=23)).isoformat(), 'original':original, 'excerpt':excerpt,
                  'addressMatched':True, 'queueMatched':True}
        return {'caseId':case['id'], 'addressFingerprint':address_identity(case), 'operatorId':operator,
                'ui':{'producer':'fixture-ui', 'result':result_ref, 'queueTree':tree, 'screenshot':self.screenshot},
                'officialReview':review, 'attempts':[{'disposition':'included', 'result':result_ref}]}

    def make_cycles(self, successes=(110,440), hours=(0,12,24)):
        previous = None
        self.cycles = []
        for index, hour in enumerate(hours, 1):
            start = datetime(2026,11,2,tzinfo=timezone.utc)+timedelta(hours=hour)
            cycle = {'schemaVersion':1, 'cycleId':'fixture-'+str(index), 'sequence':index,
                     'previousCycleSha256':previous, 'noAddressStorageSeeding':True, 'noManualQueueInputs':True,
                     'apk':{'sha256':self.apk['sha256'], 'versionCode':89, 'artifact':self.apk},
                     'runtimeCommit':'b'*40, 'androidApi':35, 'startedAt':start.isoformat(),
                     'completedAt':(start+timedelta(hours=1)).isoformat(),
                     'sampleSha256':{'baseline':digest(self.baseline_path.read_bytes()), 'holdout':digest(self.holdout_path.read_bytes())},
                     'sets':{}, 'sameResponseRegressions':[]}
            for kind, cases, count in [('baseline',self.baseline['cases'],successes[0]), ('holdout',self.holdout['cases'],successes[1])]:
                cycle['sets'][kind] = [self.make_row(case,start,i<count) for i,case in enumerate(cases)]
            for case in self.baseline['cases']:
                if case['baseline']['category']!='official_house':continue
                common = {'sourceSnapshotSha256':self.snapshot['sha256'], 'caseId':case['id'],
                          'addressFingerprint':address_identity(case), 'queue':case['baseline']['queue'], 'provenance':'official'}
                cycle['sameResponseRegressions'].append({'caseId':case['id'], 'addressFingerprint':address_identity(case),
                    'sourceSnapshot':self.snapshot,
                    'before':self.put({**common,'runtimeCommit':self.baseline['originRuntimeCommit']}),
                    'after':self.put({**common,'runtimeCommit':cycle['runtimeCommit']})})
            path = self.root / ('cycle-'+str(index)+'.json')
            write_json(path,cycle);previous=digest(path.read_bytes());self.cycles.append(path)
        return self.cycles

    def evaluate(self):
        return evaluate(self.baseline_path,self.holdout_path,self.cycles,self.root,self.protocol_path,self.sources_path)


class CapitalAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.f=EvidenceFixture(self.tmp.name)

    def test_complete_official_cycles_above_both_minimums_pass_after_24h(self):
        self.f.make_cycles((99,396));report=self.f.evaluate()
        self.assertTrue(report['passed']);self.assertEqual(report['observationHours'],25)
        self.assertEqual(len(report['remainingFailures']),55)
        self.assertEqual(report['goalPercent'],100)

    def test_90_percent_is_required_in_both_samples_not_aggregate_blending(self):
        self.f.make_cycles((98,440));report=self.f.evaluate()
        self.assertFalse(report['passed'])
        self.assertFalse(report['cycles'][-1]['sets']['baseline']['minimumMet'])

    def test_less_than_24h_or_less_than_three_cycles_cannot_pass(self):
        self.f.make_cycles(hours=(0,6,12));self.assertFalse(self.f.evaluate()['passed'])
        self.f.cycles=self.f.cycles[:2]
        with self.assertRaisesRegex(ValueError,'at least3'):self.f.evaluate()

    def test_original_sample_is_immutable_and_holdout_cannot_reuse_building(self):
        self.f.baseline['cases'][0]['exactHouse']='999'
        write_json(self.f.baseline_path,self.f.baseline)
        with self.assertRaisesRegex(ValueError,'baseline file differs'):self.f.evaluate()
        self.f.baseline_path.write_bytes((HERE/'baseline.json').read_bytes())
        self.f.holdout['cases'][0]['osmId']=self.f.baseline['cases'][0]['osmId']
        with self.assertRaisesRegex(ValueError,'reuses an original'):
            validate_samples(self.f.baseline,self.f.holdout,{**self.f.protocol,'holdoutSampleSha256':digest(canonical(self.f.holdout))},self.f.baseline_path.read_bytes(),canonical(self.f.holdout))

    def test_unconfirmed_claim_wrong_apk_missing_source_or_reviewer_cannot_count(self):
        case=self.f.baseline['cases'][0];start=datetime(2026,11,2,tzinfo=timezone.utc)
        row=self.f.make_row(case,start);cycle={'apk':{'sha256':self.f.apk['sha256'],'versionCode':89},'androidApi':35,
            'startedAt':start.isoformat(),'completedAt':(start+timedelta(hours=1)).isoformat()}
        sources={row['operatorId']:{'official.example'}}
        self.assertTrue(check_result(case,row,self.f.root,cycle,sources)[0])
        for change in [lambda x:x['officialReview'].update(provenance='public'),
                       lambda x:x['officialReview'].update(reviewer='fixture-ui'),
                       lambda x:x['officialReview'].update(excerpt='missing source text'),
                       lambda x:x['officialReview'].update(sourceUrl='https://unapproved.example/a')]:
            bad=copy.deepcopy(row);change(bad)
            with self.assertRaises(ValueError):check_result(case,bad,self.f.root,cycle,sources)
        result=read_json(self.f.root/row['ui']['result']['path']);result.pop('apkSha256')
        bad=copy.deepcopy(row);ref=self.f.put(result);bad['ui']['result']=ref;bad['attempts'][0]['result']=ref
        with self.assertRaisesRegex(ValueError,'APK hash'):check_result(case,bad,self.f.root,cycle,sources)

    def test_substantive_retries_or_source_failure_as_technical_are_rejected(self):
        case=self.f.baseline['cases'][0];row=self.f.make_row(case,datetime(2026,11,2,tzinfo=timezone.utc))
        row['attempts'].append(copy.deepcopy(row['attempts'][0]))
        with self.assertRaisesRegex(ValueError,'exactly one'):check_attempts(row,self.f.root)
        row['attempts'][1].update(disposition='technical-invalid',technicalExplanation='source returned403',reviewer='reviewer',
                                 diagnostic=row['ui']['result'],reason='source-protected')
        with self.assertRaisesRegex(ValueError,'ordinary source failures'):check_attempts(row,self.f.root)

    def test_manual_queue_or_changed_house_cannot_be_counted(self):
        case=self.f.baseline['cases'][0];start=datetime(2026,11,2,tzinfo=timezone.utc)
        row=self.f.make_row(case,start);cycle={'apk':{'sha256':self.f.apk['sha256'],'versionCode':89},'androidApi':35,
            'startedAt':start.isoformat(),'completedAt':(start+timedelta(hours=1)).isoformat()}
        sources={row['operatorId']:{'official.example'}}
        original=read_json(self.f.root/row['ui']['result']['path'])
        for mutate in [lambda r:r.update(queueEnteredManually=True),
                       lambda r:r.update(addressStorageSeeded=True),
                       lambda r:r.update(selectedHouse=case['exactHouse']+'А'),
                       lambda r:r['persistedPlace'].update(queueOrigin='public')]:
            result=copy.deepcopy(original);mutate(result);bad=copy.deepcopy(row);ref=self.f.put(result)
            bad['ui']['result']=ref;bad['attempts'][0]['result']=ref
            with self.assertRaises(ValueError):check_result(case,bad,self.f.root,cycle,sources)

    def test_holdout_file_must_be_pinned_before_queue_testing(self):
        self.f.protocol.pop('holdoutSampleSha256');write_json(self.f.protocol_path,self.f.protocol)
        with self.assertRaisesRegex(ValueError,'frozen and pinned'):self.f.evaluate()

    def test_original_38_regressions_must_all_use_identical_source_snapshot(self):
        self.f.make_cycles();last=read_json(self.f.cycles[-1]);last['sameResponseRegressions'].pop();write_json(self.f.cycles[-1],last)
        report=self.f.evaluate();self.assertFalse(report['passed']);self.assertTrue(any('all38' in e for e in report['cycles'][-1]['errors']))
        self.f.make_cycles();last=read_json(self.f.cycles[-1]);row=last['sameResponseRegressions'][0]
        after=read_json(self.f.root/row['after']['path']);after['sourceSnapshotSha256']='0'*64
        row['after']=self.f.put(after);write_json(self.f.cycles[-1],last)
        report=self.f.evaluate();self.assertFalse(report['passed']);self.assertTrue(any('inputs are not identical' in e for e in report['cycles'][-1]['errors']))

    def test_omitted_intervening_cycle_or_different_apk_identity_fails(self):
        self.f.make_cycles(hours=(0,8,16,24));self.f.cycles.pop(1)
        report=self.f.evaluate();self.assertFalse(report['passed'])
        self.assertTrue(any('history must be complete' in e for c in report['cycles'] for e in c['errors']))
        self.f.make_cycles();last=read_json(self.f.cycles[-1]);last['apk']['sha256']='0'*64;write_json(self.f.cycles[-1],last)
        self.assertFalse(self.f.evaluate()['passed'])

    def test_shared_document_host_requires_exact_officially_linked_resource(self):
        article=b'<a href="https://docs.google.com/spreadsheets/d/allowed/edit">Official roster</a>'
        proof=self.f.put(article,'html');url='https://docs.google.com/spreadsheets/d/allowed/htmlview/sheet?gid=1'
        authority={'approvedHosts':['official.example'],'linkedResources':[{'urlPrefix':'https://docs.google.com/spreadsheets/d/allowed/',
            'authorityUrl':'https://official.example/article','authoritySha256':proof['sha256']}]}
        review={'authorityLink':{'sourceUrl':'https://official.example/article','original':proof}}
        self.assertTrue(approved_source(url,authority,review,self.f.root))
        self.assertFalse(approved_source(url.replace('/allowed/','/other/'),authority,review,self.f.root))
        self.assertFalse(approved_source(url,authority,{},self.f.root))

    def test_workqueue_dispatches_all_failures_and_all22_cities_without_starvation(self):
        backlog=read_json(HERE/'failures.json');state=None;seen=set();cities=set()
        for _ in range(7):
            queue=build_queue(backlog,[],self.f.root,12,state,self.f.baseline,now='2026-11-02T12:00:00Z');state=queue['state']
            seen.update(task['caseId'] for tasks in queue['queues'].values() for task in tasks if task.get('caseId'))
            cities.update(task['city'] for task in queue['queues']['monitoring-specialist'])
        self.assertEqual(seen,{c['id'] for c in backlog['cards']});self.assertEqual(len(cities),22)
        self.assertEqual(queue['poolSizes']['independent-verifier'],72)
        self.assertLessEqual(len(state['ledger']),72*2+22*2)
        self.assertTrue(all(v['dispatches']>0 for v in state['ledger'].values()))

if __name__=='__main__':unittest.main()
