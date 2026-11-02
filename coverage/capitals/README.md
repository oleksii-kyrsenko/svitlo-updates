# Independent capital-address acceptance

The target is 100% in each of 22 oblast capitals. The minimum APK-release gate is 90%
**in both independently frozen sets**:99/110 original addresses and396/440 new
addresses. Donetsk, Luhansk and Crimea are excluded only from this test scope;
production operator capabilities are not removed. Passing these samples does
not establish coverage of every building in a city.

`baseline.json` retains the110geographic identities and the original 38 official
successes. Its SHA256 is pinned in `protocol.json`. `failures.json` contains 72
initial failure cards with owner, evidence reference and next step. Neither file
is rewritten to hide failures. Display variants already independently checked
for the original addresses are in `reviewed-display-variants.json`.

## Geographic holdout

`collect-geography.py` obtains only OSM/Nominatim data. It may reuse the original
geographic candidate archive, excludes original buildings, and retains lookup
responses and hashes. `holdout.py` freezes 20 distinct streets per city,8 central
and12 peripheral addresses, with at least 250m separation and 3 peripheral quadrants. Outskirts begin at the greater of 1.5km or 60% of
the verified city extent within the same quadrant, so elongated city shapes
do not suppress valid outskirts in another direction.
An incomplete geographic set remains incomplete; no queue data influence the
selection. Freeze and retain the candidate envelope, exact 440-case file and all
geographic artifacts before any queue lookup. Set `protocol.holdoutStatus` to
`frozen` and pin the exact file hash in `protocol.holdoutSampleSha256`. Without
this reviewed pin, acceptance fails even when the file claims to be frozen.

```sh
python3 coverage/capitals/collect-geography.py \
  --candidate-archive /path/original-map-candidates.zip \
  --output-directory /path/geographic-evidence
```

## Real UI cycle format

Use one retained signed APK and its actual SHA256. Each cycle JSON has:

```json
{
  "schemaVersion": 1,
  "cycleId": "unique-run-identity",
  "sequence": 1,
  "previousCycleSha256": null,
  "noAddressStorageSeeding": true,
  "noManualQueueInputs": true,
  "apk": {
    "versionCode": 89,
    "sha256": "64lowercasehex",
    "artifact": {"path": "candidate.apk", "sha256": "64lowercasehex"}
  },
  "runtimeCommit": "40lowercasehex",
  "androidApi": 35,
  "startedAt": "2026-11-02T12:00:00Z",
  "completedAt": "2026-11-02T13:00:00Z",
  "sampleSha256": {"baseline": "64lowercasehex", "holdout": "64lowercasehex"},
  "sets": {"baseline": [], "holdout": []},
  "sameResponseRegressions": []
}
```

The version/times above illustrate the format, not a real run or release.
`sequence` starts at 1 and increments without dropping intervening failures.
`previousCycleSha256` hashes the exact preceding cycle JSON bytes. All times are
timezone-aware ISO8601. Every artifact reference uses a relative contained path
and SHA256 of the exact retained bytes. Absolute paths, symlink escape and changed
artifacts are rejected.

Each set row identifies `caseId`, `addressFingerprint` from
`common.address_identity(case)`, and `operatorId`. Its `ui` object contains
`producer` plus artifact references `result`, `queueTree` and `screenshot`.
The result is the real Android external-driver result JSON and includes the
unchanged frozen geographic fields, `id`, `apkCode`, mandatory `apkSha256`,
`androidApi`, actual start/finish, and method `signed-apk-visible-ui` or the legacy
`released-apk-visible-ui`. A candidate is described as a candidate, regardless
of the legacy driver's method label.

An official success requires `outcome: queue_found_official`,
`addressSelectedThroughUI: true`, `saved: true`, no `uiIssues`, matching selected
city/street/type/exact house, `visibleQueue` and app-written `persistedPlace`.
The saved place must have the same address, operator, `queueOrigin: official`,
`queueConfirmed: true`, queue and source scope. The same queue must appear with
its label in the real accessibility XML. Retain a real Android PNG as well.
Unsuccessful cases also retain their actual result, XML and screenshot, and
remain in the denominator. Queue entry and address/storage seeding are forbidden.

Each row's `attempts` contains exactly one `included` result reference. An extra
attempt may only be `technical-invalid`, with `technicalExplanation`, reviewer,
original diagnostic artifact and one of `automation-input`,
`automation-navigation`, `emulator-system-failure`. An ordinary protected source,
not-found result or timeout at the operator is not a technical discard. Fixing a
harness error does not permit replacing the target address.

### Independent official-source review

`officialReview` is a separate review of the original source, not a copy of the
app's official label. Required fields:

- `method: independent-original-source`, named `reviewer` different from UI
  producer, and the exact `addressFingerprint`/`operatorId`/`queue`/`scope`.
- `provenance: official`, `unambiguous: true`, `sourceUrl`, original `observedAt`
  and `expiresAt` (at most 24 hours; valid when the UI result was recorded).
- `original` artifact reference, literal supporting `excerpt`,
  `addressMatched: true` and `queueMatched: true` after checking the original.
- For PDF/OCR extraction, an `extractedText` artifact and
  `extractedFromSha256` equal to the original hash. An excerpt must exist in that
  text. Extraction still requires independent checking against the original.
- For street/settlement/territory-wide assignments,
  `explicitWholeScope: true` and `boundariesAndExclusionsChecked: true`.

Official source hosts are operator-specific in `source-authorities.json`.
A reachable homepage does not approve an address API. Added API hosts retain
reviews linking the official frontend assets, their hashes and the explicit
API configuration. Unverified new hosts remain ineligible until reviewed.

Shared Google hosting is **not** approved globally. Only the precise spreadsheet
IDs linked by the reviewed Zaporizhzhia official article are eligible. A source
review for those rows additionally supplies:

```json
{
  "authorityLink": {
    "sourceUrl": "exact-official-article-URL-from-policy",
    "original": {"path": "original-official-article.html", "sha256": "64lowercasehex"}
  }
}
```

The official article hash must match the reviewed policy and its original HTML
must contain the actual spreadsheet link. A changed article is reviewed before
the allowlist hash changes. A different spreadsheet on the same host is rejected.

### Original 38 regressions and the 24 hour gate

Each cycle also includes exactly 38 `sameResponseRegressions`. Each row identifies
`caseId` and `addressFingerprint`, plus artifact references `sourceSnapshot`,
`before`, `after`. The before/after executable-comparison results must identify
that case/fingerprint, the *same* `sourceSnapshotSha256`, the original official
queue and `provenance: official`. Their `runtimeCommit` fields identify the
original build 88 runtime and the candidate runtime respectively. This tests
preservation on identical inputs separately from a live source changing its data.

```sh
python3 coverage/capitals/acceptance.py \
  --holdout /path/frozen-holdout.json \
  --cycles /path/cycle-1.json /path/cycle-2.json /path/cycle-3.json \
  --artifacts /path/retained-evidence \
  --output /path/acceptance-report.json
```

The checker exits nonzero unless the latest 3 consecutive, non-overlapping cycles
use the same APK, meet both 90% minimums and span at least 24 hours. It reports every
remaining failure and city totals toward 100%. All chronological cycle records
must be retained; local code cannot detect an intentionally omitted remote run.
Android 11/15/16 native screenshots, upgrade from 88 with data retention, manual
correction/offline-cache preservation, bad signature/expiry/revocation checks
are additional mandatory release gates; this command does not replace them.

## Seven bounded work roles

```sh
python3 coverage/capitals/workqueue.py \
  --state coverage/capitals/work-state.json \
  --output coverage/capitals/workqueue.json
```

Persist the state between scheduled runs. Per-role cursors fairly rotate all 72
initial failure cards; coordinator and monitoring include all 22 cities, including
cities where all 5 original cases succeeded. A bounded dispatch ledger records
counts and first/last dispatch times. Dispatch does not mean a model executed a
task, an integration works, or coverage improved. These are free batch roles;
there are no seven continuously running paid models or paid permanent server.
The existing local CPU model may assist research/extraction.

Optional `--reports report1.json ... --artifacts /path/evidence` validates reports
before advancing persistent state. A report needs `reportId`, known `role` and
`caseId`, `observedAt`, `producer`, independent `reviewer` with
`reviewerRole: independent-verifier`, HTTPS `sourceUrl`, original `artifacts`,
`findings`, `nextStep`, and status `source-verified`, `adapter-verified`,
`resolved-official` or `blocked-with-evidence`. A claimed resolution also needs
`acceptanceCaseEvidence`. Reports retain findings; they do not mutate the frozen
backlog or establish a release percentage. Blockers remain active toward 100%.

## Current status

The baseline and failure backlog are frozen. Geographic holdout status and its
reviewed hash are recorded in `holdout.json` and `protocol.json`; retained
geographic evidence lives separately. A geographic freeze does not establish
any queue coverage. Candidate UI/source verification, the 90% gate, the native
matrix and release are separate jobs. Synthetic tests never contribute to the
coverage percentage. Use the actual retained run reports for progress.
