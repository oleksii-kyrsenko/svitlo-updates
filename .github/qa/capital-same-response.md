# Pinned-source queue regression

This generic external harness imports application code only from separately
provided private runtime directories. Do not copy private application source
into this public QA repository.

It checks the original38 successful addresses against the original and candidate
runtime using the same immutable source-response snapshot. Both replay passes
forbid network access; missing requests fail explicitly. The source trees must
match their declared Git commits. Input comes from original audited UI address
selectors with every saved queue field removed.

```sh
NODE_USE_ENV_PROXY=1 node .github/qa/capital-same-response.mjs \
  --record --anonymous-session --prepare-old \
  --old-root /temporary/original-runtime --candidate-root /private/app \
  --candidate-commit <candidate-runtime-commit> \
  --baseline <frozen-baseline.json> --original-summary <original-UI-summary.json> \
  --out <new-evidence-directory>
```

`--anonymous-session` supplies normal public HTTP source cookies and the prior
source page's Referer in memory, and uses the application's browser-fetcher
interface for supported sources. This does not run Chromium/JavaScript or solve
a browser challenge. Cookies and authentication headers are never written to
snapshots. ASD subscriber fields are discarded; Cherkasy subscriber references
are pseudonymized in memory and fixture keys.

Reproduce existing evidence without live requests:

```sh
node .github/qa/capital-same-response.mjs --replay \
  --old-root /temporary/original-runtime --candidate-root /private/app \
  --candidate-commit <candidate-runtime-commit> \
  --baseline <frozen-baseline.json> --out <existing-evidence-directory>
```

Do not overwrite a source snapshot. A technical transport correction uses a new
evidence directory, retains the previous attempt and explains the correction.
`--case-ids` is for explicit diagnostics; a subset cannot pass the38-case gate.
A source failure or natural change of queue is a blocker, not a preserved queue.
This check is separate from actual Android UI coverage and cannot count toward
99/110 or396/440.

Verified3November2026:36of38 original expected queues reproduced in both pinned
runtimes, zero candidate-only regressions and zero replay misses. The Dnipro case was recovered by actual ordinary Chromium source capture in public
CI run41592098789 and both pinned runtimes return5.2 without network during replay.
Two Cherkasy cases remain blocked by official-source unavailability; their browser
captures contain no responses and cannot establish a successful regression. The
full38 gate remains failed.
Proofs: `capital-coverage-90/same-response-combined-browser-41592098789/report.json` in the
session's retained Library, including the original attempt ledger.

The separate `browser-regression-capture.yml` workflow can capture the selected
source protocols using ordinary Chromium on the public CI network.
It contains only source-side HTTP code and frozen public QA inputs. It stops at
visible CAPTCHA/login, never solves challenges, and persists no cookies or raw
subscriber identifiers. A complete capture is still only source evidence; run
both pinned private runtimes locally against that exact snapshot before claiming
a preserved result. An incomplete source capture remains an explicit blocker.

The source capture can restrict work to request.caseIds, without revisiting passed
cases. Safe fixed error codes distinguish TLS certificate/protocol, DNS, timeout
and connection-reset blockers; raw browser exception text and private query
references are never persisted. The committed request selects only the two unresolved
Cherkasy cases. This is source diagnosis, not a retry selected to improve coverage.

Focused public CI run41636605058 (3November2026, commitca3b8dd) completed the
diagnostic workflow, but both cases stopped at `official-tls-certificate-error`
on their first address API request, after the ordinary official page rendered.
Both captures have `captureComplete:false` and no response fixtures or queue
proofs. Workflow success therefore does not change the36/38 regression result.
The exact original artifact ZIP SHA256 is
`805eee07f5b9ef1117998c9c62171a529e85353fde515c758f5d803008c9100d`.
Retained proof directory: `capital-coverage-90/browser-regression-41636605058/`.
TLS verification remains enabled.
