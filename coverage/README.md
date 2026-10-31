# Dynamic coverage operations

This directory contains public-data tooling, not application source. Existing public-evidence/Qwen and document-cache jobs remain independent. Queue/address mappings are harvested at runtime; neither samples nor expected queues are built into the app.

- `monitor.py` probes every configured OSR (32 at bootstrap), classifies HTTP protection separately, collects document/channel leads and checks the current NERC registry index. A reachable page is **not** an integrated address service. Links are research leads, not facts. The registry check detects register URL changes; legal status review remains an agent task.
- `collect-asd.py` harvests bounded official ASD street dictionaries. Connections with missing, unknown or different queues are omitted; only unanimous house values enter an official bundle. Original API provenance, official street identifiers and observation time survive. Subscriber accounts/EIC are discarded before persistence. Default scheduled exploration rotates cities; one batch is partial coverage, not a national audit.
- `build.mjs` checks public normalized records and signs an envelope with Ed25519. A new parser is installed here; the phone consumes the unchanged data contract. Compatible operator/source changes do not need a new APK.
- `refresh.mjs` publishes only fresh successful collections and preserves unexpired previous bundles with their original timestamps. It never extends stale evidence. If no valid bundle remains or signing is unavailable, no new manifest is published.

The six-hour public workflow runs controls, health checks, discovery leads, optional signing and data publication. It maintains one investigation issue after repeated source failures or a regulator-index change. Signing uses `DYNAMIC_COVERAGE_SIGNING_KEY`, an Ed25519 PKCS8 PEM GitHub Actions secret. The secret is never a repository file, workflow artifact or log. `DYNAMIC_COVERAGE_KEY_FILE` selects a local protected file for manual execution.

The client pins the matching public key and verifies signature, bounds, SHA256, age and schema. Content-addressed bundles and their manifest commit together. To roll back, sign a higher revision referencing the previous still-valid bundles; to disable, run `DYNAMIC_COVERAGE_KEY_FILE=/protected/path/private.pem node coverage/disable.mjs` and publish the signed higher revision. Do not rewrite source observation times. Old APK/public-evidence/cache paths remain intact.

## Current bootstrap and operational limitation

Bootstrap source health: 24 available pages, 4 protected, 4 unavailable in this workspace. These are not address success rates. The bounded Lviv official collection produced 586 house records in its first live pass, with three street failures; see the separately retained harvest report. No fresh 20-address-per-OSR national audit is claimed.

The current connected GitHub identity returns HTTP403 for Actions secret public-key access, so it cannot install the signing secret. A local protected key and matching client pin have been generated. Local signing works; unattended signed publication requires that same key to be provisioned as the named secret. The workflow fails explicitly and preserves the previous signed manifest while the secret is absent. Do not replace it with an unsigned publisher or put a private key in this public repository.

## Agent responsibilities

Coordinator owns baseline, regression triage and rollout. Three researchers own disjoint OSR groups and search official sources, municipalities, local sites and public channels. Address specialist owns adaptive matching. Independent verifier compares evidence and unchanged old behavior. Automatic collection continues between agent sessions; the existing free Qwen batch job remains available for its existing extraction tasks. No paid persistent service or hosted inference API is introduced.
