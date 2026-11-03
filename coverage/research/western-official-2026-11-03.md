# Current western official address sources, 2026-11-03

## Prykarpattia / Івано-Франківськ

The operator's current official information section is
<https://oe.if.ua/uk/sections/5e9f1c5fdb9c42704449b999>.
Its **Графіки погодинних вимкнень** section explicitly publishes the period
2026-10-01 through 2027-04-01 and links all twelve GPV subqueue PDFs.
The separate GAV section is not used. The operator's current article
<https://oe.if.ua/uk/articles/6ac4e15616a2a8dc80247cf3>, dated 2026-10-06,
also directs readers to the address lists in this official section.

The source is reachable with ordinary HTTP. One practical discovery was that
its HTML arrived gzip-compressed even without an explicit compressed-response
request. Python urllib does not automatically decompress this body. The new
collector handles bounded normal gzip decoding; it does not bypass any access
challenge or use browser stealth.

`collect-western-official.py` reads all currently linked GPV documents before
releasing a packet. It verifies the current period, all 12 unique subqueues,
operator-only document URLs and matching row queue fields. Only rows with the
exact city cell Івано-Франківськ and district Івано-Франківський are retained.
Neighbouring localities in the same district do not count as this city.

Only literal house identifiers assign queues. No numeric range expansion,
whole-street inference, neighbour interpolation or substitution of GAV for GPV
is performed. Conflicting literal assignments, qualified/partial house tokens
and potentially conflicting ranges cause abstention. Street types printed in
the source are preserved; no invented address aliases are introduced.

An initial actual run stopped on the source token 400-2 because it resembled a
reversed range. The parser was corrected to abstain on that token, including a
veto of a separately claimed bare 400, rather than reinterpret it as 400/2.
The first failed report is retained in the proof archive. A second actual run
fetched all 13 official responses and completed without errors.

Successful observation began 2026-11-03T20:57:21.484Z. The resulting packet has
624 compact rows containing 10,297 positive literal house facts, 10,694 observed
houses and 397 abstentions. Original observation times and 24-hour expiry are
preserved. These are source-derived records, **not measured Android coverage**
or a claim that the source contains every city address.

Publisher `validateBundle`, `cityShards` and `validateCityShard` passed. The
phone city shard is 466,122 bytes, below the 8 MiB ceiling. Thirteen meaningful
Python checks cover current periods, complete document sets, GAV separation,
gzip bounds, exact city scope, queue conflicts, literal suffixes, partial houses,
ranges and bounded output chunks.

Reproduction (uses the existing public CI dependency pdfplumber):

```sh
python3 coverage/collect-western-official.py \
  --operator prykarpattia --target-city Івано-Франківськ --full-city \
  --request-limit 16 --output /tmp/prykarpattia.json \
  --state /tmp/prykarpattia-state.json \
  --evidence-directory /tmp/prykarpattia-originals
python3 coverage/qa/test-western-official.py
```

Permanent local proof:
`/workspace/library-files/capital-coverage-90/western-official-nov3/prykarpattia-current/`.

* `prykarpattia.json`: 3,073,023 bytes,
  SHA256 `c970f7b00f8ad16af97088858dbe3f2e471edffbaad20cf598327caa1425dc55`.
* `official-public-source-proof.zip`: 7,402,183 bytes,
  SHA256 `a45ece236e857fd60ccf6a64b4e84eb1e96111924e947f515199609de7eed8df`.

## Volyn / Луцьк

The existing current public form remains
<https://www.energy.volyn.ua/spozhyvacham/perervy-u-elektropostachanni/cherga/>.
It displays separate GPV and GAV columns and allows ordinary city/street POST
queries. It exposes no verified complete-city directory contract.

The previous source cursor already discovered 492 street names. This proves
earlier discovery, not current availability or full-city coverage. Examination
of the actual capital-priority CI run 41650822032, rather than the separate
legacy/global run, shows both its discovery POST and exact-street followup POST
received HTTP 403. This was not an argument-parser failure or an exhausted
request budget. Without the 403 response body, attributing it specifically to
Cloudflare would be speculative.

The existing same collector works with ordinary workspace requests. A new
bounded 400-request traversal starts from the retained city cursor and does not
use the frozen benchmark addresses. Every original HTTP response is retained
for independent verification. Its result will be recorded separately; a
successful workspace read does not establish reliable hosted CI renewal.

The original capital CI artifact and exact per-operator reports are retained
under `western-official-nov3/`. Artifact SHA256:
`6fafa1936636169527150b13d1f4b553d5858dd39d1c57d305ea7f5c78d4bc88`.
