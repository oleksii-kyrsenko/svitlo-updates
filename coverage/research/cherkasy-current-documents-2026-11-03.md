# Cherkasy official urban house lists

Source: https://www.cherkasyoblenergo.com/perelik-gpv (observed live on
2026-11-03, 12:25 UTC). This official index links one PDF for each of twelve GPV
queue/subqueue combinations. Index labels and original PDF headings agree on
the effective period **2026-10-01 to 2027-04-01**. These are effective dates,
not publication timestamps. The collector does not invent a publication date.

`collect-cherkasy-documents.py` reads the index and **all twelve original PDFs**
before releasing any facts. The PDFs' ruled department cells identify
`Черкаські міські ЕМ` / `Черкаська міська філія`; page continuations retain that
department scope. Names from regional branches, other towns and villages do
not establish Cherkasy city facts.

Only literal enumerated house identifiers are published. An unqualified range
has no assumed parity or extent; it is never expanded. Cross-queue conflicts,
apartment-only connections and unresolved street/lane identity cause
abstention. Explicit lane/boulevard/avenue/descent types are preserved. Bare
names require a source list category or an unambiguous explicitly typed name
elsewhere in the same complete document set. No address fixture, timetable
hours or emergency/GAV group establishes a queue.

The final live run used thirteen ordinary GET requests and produced:

| Result | Count |
| --- | ---: |
| Compact positive records | 510 |
| Literal positive house facts | 12,491 |
| Exact house observations | 13,430 |
| Conflict / partial / ambiguous house abstentions | 939 |

The publisher validates the resulting 3,407,462-byte bundle. Its SHA256 is
`b2bda95ad47f9afee5b1ce729181f85d51462405c173fd1e09a9aa578de2d13a`.
Observation time is the oldest fetch in the complete set,
2026-11-03T12:25:49.654Z; expiry is at most 24 hours after that observation and
never beyond the effective period. Re-reading an archived file cannot refresh
its original observation age.

These counts describe source extraction. They are **not Android UI coverage**,
an exhaustive inventory of every city address or proof of the 90% acceptance
target. `dictionaryComplete` remains false; complete traversal of the twelve
current official documents is reported separately.

All original PDFs, index HTML, source hashes/URLs/queue labels, department
boundaries and verbatim urban-cell excerpts are retained in the workspace
evidence directory
`library-files/capital-coverage-90/cherkasy-current-documents-2026-11-03/`.
The source-side normalized bundle is `cherkasy.json`; provenance is
`cherkasy.json.report.json`; raw files are content-addressed under `raw/`.

Reproduction (requires the already used public CI dependency `pdfplumber`):

```sh
python coverage/collect-cherkasy-documents.py \
  --operator cherkasy --target-city Черкаси --full-city \
  --output /tmp/cherkasy.json --state /tmp/cherkasy-state.json \
  --request-limit 16 --evidence-directory /tmp/cherkasy-public-source
python coverage/qa/test-cherkasy-documents.py
```

The minimum successful fetch budget is thirteen. A missing PDF, changed table
geometry, heading/index discrepancy, incomplete queue set or request failure
releases no partial positive or negative facts. The previous bounded snapshot
can therefore remain valid under the normal publisher merge/expiry policy.

The current PDF set does not literally establish Кавказька 231 or
Старицького 2. The urban Кавказька enumeration is in queue 4.1, pages 20/21/25;
Старицького М. is in queue 3.1, page 23, with other explicitly enumerated houses.
Neither nearby street names nor neighbouring house identifiers can recover
those two exact old API successes.
