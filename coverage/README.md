# Dynamic coverage operations

DTEK audit, 1November2026: all seven sites in the state source directory are
registered. PEM/VVM collectors now use `/ua/shutdowns-schedule`, matching the
native registry. City-only legacy selectors remain on their original street;
new streets cannot reuse that selector. Publisher validation refuses one
explicit identity shared by unrelated streets. Revision12 retains40 previous
Dnipro/Odesa house entries and adds40 fresh source-derived entries. This is
not an independent address-coverage audit or proof that protected sites work.
The verified Kharkiv canonical source link is now in `sources.json`; its
Turnstile form is still unintegrated. See `research/svitlo-app-2026-11-01.json`.
Hosted run41324880451 subsequently passed18Node/32Python controls and published
revision13:36 Kyiv-region,60 Dnipro and40 Odesa house entries. All59 prior DTEK
source-derived ready cases and77 added entries match the shipped client. This
does not establish independent coverage gains or successful access to all seven
networks. A follow-up abbreviation-spacing fix passed all9merge controls locally.

Latest verified operation, 1November2026: hosted run41321360024 published
revision10 with11 operator datasets. Revision11 additionally includes a
workspace-collected Chernivtsi snapshot:25,618 explicit source house entries,
20 source rereads, original observation times and expiry preserved. The hosted
runner receives HTTP403 for Chernivtsi; automatic renewal for this operator is
not established. See `manual-refresh-2026-11-01.json`. These are partial source
datasets, not full coverage of12 operators or independently verified new
addresses. Failed/unsupported collection remains visible in the single
investigation task even when a source home page is reachable. APK channel88 is
unchanged by these data publications.

This directory contains public-data tooling, not application source. Existing public-evidence/Qwen and document-cache jobs remain independent. Queue/address mappings are harvested at runtime; neither samples nor expected queues are built into the app.

- `monitor.py` probes every configured OSR (32 at bootstrap), classifies HTTP protection separately, collects document/channel leads and checks the current NERC registry index. A reachable page is **not** an integrated address service. Links are research leads, not facts. The registry check detects register URL changes; legal status review remains an agent task.
- `collect-asd.py` harvests bounded official ASD street dictionaries. Connections with missing, unknown or different queues are omitted; only unanimous house values enter an official bundle. Original API provenance, official street identifiers and observation time survive. Subscriber accounts/EIC are discarded before persistence. Scheduled exploration resumes from the persisted `crawl-state.json` city/street cursor: successive street slices, then the next city, then a full-cycle wrap. No first-eight-streets or 2000-city ceiling remains. One batch is partial coverage, not a national audit. `COVERAGE_STREET_BUDGET` (repository variable, default8, maximum50) bounds house-list requests per run. A failed street/list retries across three runs, then progresses for that cycle and is revisited after wrap. The cursor contains only numeric positions/source IDs and retry counts; it is committed even after a failed collection/signing attempt.
- `build.mjs` checks public normalized records and signs an envelope with Ed25519. A new parser is installed here; the phone consumes the unchanged data contract. Compatible operator/source changes do not need a new APK.
- `refresh.mjs` publishes only fresh successful collections and preserves unexpired previous bundles with their original timestamps. It never extends stale evidence. If no valid bundle remains or signing is unavailable, no new manifest is published.

The six-hour public workflow runs controls, health checks, discovery leads, optional signing and data publication. It maintains one investigation issue after repeated source failures or a regulator-index change. Signing uses `DYNAMIC_COVERAGE_SIGNING_KEY`, an Ed25519 PKCS8 PEM GitHub Actions secret. The secret is never a repository file, workflow artifact or log. `DYNAMIC_COVERAGE_KEY_FILE` selects a local protected file for manual execution.

The client pins the matching public key and verifies signature, bounds, SHA256, age and schema. Content-addressed bundles and their manifest commit together. To roll back, sign a higher revision referencing the previous still-valid bundles; to disable, run `DYNAMIC_COVERAGE_KEY_FILE=/protected/path/private.pem node coverage/disable.mjs` and publish the signed higher revision. Do not rewrite source observation times. Old APK/public-evidence/cache paths remain intact.

## Current bootstrap and operational limitation

Bootstrap source health: 24 available pages, 4 protected, 4 unavailable in this workspace. These are not address success rates. The bounded Lviv official collection produced 586 house records in its first live pass, with three street failures; see the separately retained harvest report. No fresh 20-address-per-OSR national audit is claimed.

The connected identity returned HTTP403 for Actions secret management; the user installed the named secret separately. Hosted run [41200570297](https://github.com/oleksii-kyrsenko/svitlo-updates/actions/runs/41200570297) passed collection, signing, integrity verification, publication and cursor persistence. It published revision3 with736 records (586 earlier Lviv records retaining original times, plus150 freshly collected Brody records). A prior timestamp validation bug was fixed in9976eab. If the secret is absent in the future, publication fails explicitly and preserves the previous signed manifest. Do not replace it with an unsigned publisher or put a private key in this public repository.

## Agent responsibilities

Coordinator owns baseline, regression triage and rollout. Three researchers own disjoint OSR groups and search official sources, municipalities, local sites and public channels. Address specialist owns adaptive matching. Independent verifier compares evidence and unchanged old behavior. Automatic collection continues between agent sessions; the existing free Qwen batch job remains available for its existing extraction tasks. No paid persistent service or hosted inference API is introduced.

## Multi-operator normalized collectors

The registry covers all32 operator identities. A registry entry or successful web
page is not proof of a working queue assignment. Four bounded workers invoke
standalone official API/HTML/PDF collectors; empty, protected and unsupported
sources are reported separately. Fresh valid assignments are merged with only
unexpired prior data. Failed collectors do not renew prior observations.

`COVERAGE_ADDRESS_BUDGET` defaults20 address checks (batchA needs up to80 source
requests); `COVERAGE_STREET_BUDGET` defaults8. Per-host rate limits and subprocess
budgets bound collection. Cursors and sourced community metadata persist between
runs. Public geography bootstrap values retain original provenance and expiry;
no municipality is invented from a city name. Historical client ID UA-73 is
matched to published ISO UA-77 without changing existing app storage IDs.

Literal house groups compact identical source observations without extending
any deadline. Partial house batches replace observed houses only. Different
street identities remain distinct. Settlement-wide rows require explicit whole
settlement wording in the publication; their count is not a count of houses.

Batch reports distinguish source-derived checks, rereads, unresolved geographic
context and protection. They are not a nationwide random address audit. Public
message collection remains independent and may legitimately accept zero records.
