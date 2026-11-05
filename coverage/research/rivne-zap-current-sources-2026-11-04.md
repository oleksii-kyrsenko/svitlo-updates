# Current official city source review — 2026-11-04

## Rivne

The active operator page `https://www.roe.vsei.ua/disconnections` currently links
`https://www.roe.vsei.ua/wp-content/uploads/2026/10/GPV_cherga_misto_Rivne-1.pdf`.
Two ordinary HTTPS GETs returned200. The city PDF contains two pages, three-column
tables, and all twelve GPV subqueues. The independent capital directory supplies
the city/community context; no Nominatim request is required during collection.

New isolated collector `collect-rivne-zap.py --operator rivne --target-city Рівне
--full-city --request-limit4 --output ... --evidence-directory ...` reads that
active attachment, preserves original row quotations, and emits literal houses
or ranges with an explicit finite parity/all marker only. Bare street names,
partial areas, businesses, and unqualified ranges do not become assignments.
An uncertain range still vetoes contradictory literal claims in another queue.
All twelve subqueues and the city heading are required before any publication.

The old decoder returned repeated provenance IDs when one PDF row mentioned the
same road twice; the generic publisher's last-ID-wins deduplication then lost an
earlier house list. The new collector unions those exact lists under the shared
ID after checking conflicting queues. It also prevents an explicitly even range
from vetoing an odd literal house in another queue.

Actual final packet:198 provenance rows,1012 house facts before cross-row
deduplication,934 unique street/house/queue facts. Public revision27's city shard
contains915 such unique facts: **19 added,0 removed**. Nine Python checks pass.
Publisher, city shard and actual private-client validation pass; the phone packet
is193067 bytes. A source-derived full street-type spelling matches correctly,
while a different settlement is rejected.

Raw decoded source labels often omit the space in `вул.Соборна`; the new collector
inserts it after an explicit abbreviation. **This is not a newly discovered cause
of the Android failures:** the existing publisher already canonicalizes that
spacing. The real incremental facts come from correct repeated-road merging and
conservative range handling.

The five frozen Rivne baseline addresses were reviewed only after the parent
authorized failure diagnosis, without reading expected queues. Their exact house
identifiers are absent or the PDF gives only an unqualified bare street. No
explicit whole-street marker was found. None of these five can truthfully be
counted from this document; no holdout address was inspected for tuning.

Permanent evidence: `/workspace/library-files/capital-coverage-90/rivne-zap-nov4/`.
See `rivne-summary.json`, `rivne-validation.json`,
`rivne-factset-and-baseline-diagnosis.json`, and
`rivne-original-source-proof.zip`. These are source facts, not Android coverage.

## Zaporizhzhia

The legacy operator URL now redirects to `https://www.zoe.com.ua/outage/` and is
readable with ordinary HTTPS. Its city roster article currently contains only
eleven spreadsheet links, omitting subqueue2.1. More importantly, the current
operator page directly links an anonymous city address checker:

`https://script.google.com/macros/s/AKfycbwFgBo9W8JL_7FqghJ1hDiE-Fyxzs4GZJAq2xhTseOiv5ZnkusMKj0_g9R0DJKko19r/exec`

Its public frontend calls `google.script.run.getData()` automatically on load.
Static source code establishes the columns:0street,1house,2GPV,3ZOVA/partial
exemptions,4GAV. Empty GPV and GAV must never be promoted to a GPV assignment;
partial exemptions and multiple connections require abstention.

A separate read-only Chromium CI probe captures the ordinary frontend's public
dictionary after validating the active operator link. It submits no account,
EIC, household or login request and persists only public address/GPV columns plus
a boolean exemption flag. Extra fields, exemption text, cookies, authentication
headers and session tokens are not retained. The dictionary is not signed or
published by this diagnostic workflow. Actual results are recorded separately.

### Completed anonymous dictionary capture and safe partial normalization

Normal Chromium run41901079026 completed successfully. The original artifact ZIP
is139801 bytes, SHA256
`26de30d7584932d7d79889ad64bf23124e32d30842ecb7f4ab2a39f1d85feec0`.
The actual frontend function source was retained separately (SHA256
`f24f38eaddce17dd454d895aa0041109f893860d395cac18a370f61053a1168f`).
`loadData` assigns the returned data directly. `loadHouses` matches each row's
street exactly, and `showQueue` independently filters every row by exact street
and house before reading GPV/ZOVA/GAV. There is no inherited locality-heading
state. The operator's active link explicitly names the city; recognized towns,
locality-qualified labels and landmarks never inherit that default.

The source includes outliers such as a town label with the road in the house
field, and an explicitly rural street. Their neighbouring rows are retained in
`zap-geography-scope-proof.json`. Both are rejected rather than treated as city
addresses. As an additional independent geography check, the public postal
classifier was queried using the city and district IDs it returned itself;
3168 of the3350 final positive facts match554 exact city road labels. Postal
data supplies no queue and does not replace the operator's city-scope proof.

Four long house fields remain privacy/unsupported quarantines, bound only by
normalized road SHA256. All28 otherwise recognized literal houses on those
three roads abstain. No private field, unknown house, account identifier, GAV
value or raw ZOVA exemption text is retained in the projection. Ambiguous `пр.`
labels are not silently recast as avenues or drives.

The partial decoder `collect-rivne-zap-app.py --projection ... --output ...`
uses only literal houses. Pipe encodings and ranges generate no positive
addresses; they only veto already observed literal candidates when another
GPV, unknown GPV or exemption could apply. This deliberately does not assert
that a pipe is a slash or a proven list. Any literal connection with an unknown
GPV or ZOVA flag vetoes a whole-house assignment even when another row contains
a valid GPV value. No complete-snapshot or completed-street flags are emitted.

Final packet `zaporizhzhia.json`:3350 positive literal-house facts,6340 observed
literal identities,2990 abstentions. Reasons:613 ZOVA exemptions,1895 unknown
GPV connections,46 conflicting GPV values,408 overlapping unsupported encodings,
and28 quarantined-road cases. Another587 source rows fail typed-road/locality
scope and5797 house encodings only provide uncertainty constraints. These are
source extraction counts, not Android coverage.

Packet SHA256:
`21c103cf37265a3a7c3bcc3dbb1f09d6e843e21738135ebf1c1c2095cdc70ad1`;
4118760 bytes. Seventeen decoder checks pass, including unknown-connection/ZOVA
veto, conflicting suffix spellings, no pipe/range invention, geography rejection,
original authority expiry/hash and GPV/GAV schema separation. Publisher and
actual client validation pass. All102 independently sampled source-derived
literal lookups return the source's queue; another city is rejected. The phone
city packet is2612506 bytes, below8MiB.

Actual dictionary observation:2026-11-04T19:57:50.212Z. Expiry is deliberately
limited by the previously reviewed official authority to2026-11-05T11:36:08.768Z.
The ordinary hosted request to the operator parent timed out, so the original
unexpired parent HTML was used only as link authority. The dictionary itself was
freshly fetched. A readable deletion or changed link always stops collection.
Automatic renewal of this authority has not been established; the read-only
workflow never signs or publishes data.

### Scheduled publisher added on November5

`zaporizhzhia-city-coverage.yml` now reads the same reviewed deployment every six
hours using ordinary free Chromium. It shares the existing
`dynamic-coverage-publisher` concurrency group, validates and merges source
observations, verifies both signatures and stages only current index references.
The existing signing secret is used; the APK update channel is untouched.

A fresh readable official parent must still actively link the exact reviewed
city deployment. Only such an actual reread may refresh the retained authority
cache. During a temporary parent timeout/5xx, the prior original may be reused
only until its original expiry; signing or repacking never renews it. Changed,
removed, denied or expired authority aborts collection and leaves remote data
unchanged. The scheduled hook alone does not establish that hosted parent reads
or subsequent automatic renewal work: the first full hosted run must be reviewed.

Full provenance/abstentions/validation/summary and the609944-byte source-proof ZIP
are in the permanent `rivne-zap-nov4/` evidence folder. Source-proof ZIP SHA256:
`1054e93cfbfbe0776fb704307635cdd8cbdf017d58bb453422bc3d497df86e1c`.
