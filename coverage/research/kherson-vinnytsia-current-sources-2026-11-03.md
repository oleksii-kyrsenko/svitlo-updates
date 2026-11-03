# Current official source investigation, 3 November 2026

## Vinnytsia: current public PDF found and collected

The old GPV URL redirects to an archived document index. Its current navigation
links to https://voe.com.ua/informatsiya-pro-cherhy-hrafika-pohodynnykh-vidklyuchen-hpv-1 .
That active page links to
https://voe.com.ua/sites/default/files/2026-09/gpv-2026-2027-na-sayt.pdf .
Both title and PDF establish the period1 October2026–1 April2027.
Ordinary HTTP with a public browser User-Agent and this same-origin Referer
successfully read the page and PDF. No challenge, authentication, alternate
proxy or TLS bypass was used. The existing online Drupal address form still
returned403 during this investigation; that does not block this separate source.
The bare-host `/disconnection/detailed` URL redirects to
https://disconnection.voe.com.ua/ and returns403 there, so the earlier Drupal
form assumptions also need revalidation against the current frontend.

`collect-vinnytsia-documents.py` discovers the current PDF from its active index
and checks its period again in the actual PDF. It reads the municipal `СО "ВМЕМ"`
section, stopping at the next department, including a boundary halfway down a
page. Explicit other-locality paragraphs are excluded. The unruled source uses
centred queue labels; only text paragraphs whose complete vertical bounds contain
one distinct queue are used. Ambiguous label/paragraph boundaries abstain.

The actual two-GET CLI run produced128 compact records with593 positive literal
houses from764 observed houses;171 observations abstained after contradictory,
partial or range evidence. The entire municipal section and all twelve queue
labels were read. This is not a complete city address inventory. Numeric ranges
are never expanded, ranges veto conflicting literals in another queue, numbered
lanes are omitted until their name grammar is supported, untyped street names
can veto but cannot become positive guesses, and apartment/entrance qualifiers
cannot establish the full house. Source observation times are retained.

The publisher and exact candidate client validators passed. The city shard is
183122bytes, below the existing8MiB limit. Ten focused tests cover current/expired
index selection, authority, active-vs-commented links, actual PDF columns, queue
ambiguity, locality/department boundaries, suffixes, initial/house separation,
numbered-lane ambiguity, ranges, conflicts, and partial-house abstention.

The permanent handoff directory is
`library-files/capital-coverage-90/kherson-vinnytsia-nov3/`.
`vinnytsia.json` is the final normalized candidate; `source-summary.json` pins its
SHA and original observation times. `official-current-source-proof.zip` contains
the two original responses and parser report. An earlier offline parse is
explicitly retained as `offline-pre-hardening-diagnostic.json`, not publishable
facts. This source read is not an Android UI coverage result.

## Kherson: public site, account-bound queue service

https://ksoe.com.ua/ and https://ksoe.com.ua/cabinet/login/ both returned200.
The homepage's old `/disconnection/`, `/disconnection/schedule/` and
`/disconnection/search/` navigation and service tile are inside HTML comments;
they must not be treated as active anonymous address services. The active
personal-cabinet page exposes username/password login, account registration and
recovery forms, with no public GPV address roster. No login or account workflow
was submitted. Current public search did not establish a current official
municipal address-to-queue mirror. Consequently no Kherson queue facts are
emitted, and a generic third-party claim that the operator has address search is
not promoted to an integration.

The original anonymous homepage/login HTML and HTTP hash/status report are
retained in the handoff directory. Next useful paths are an actual current
official municipal roster or an operator-supported anonymous source. Merely
retrying the login or assigning a nearby street's queue cannot close this gap.
