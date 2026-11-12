# Candidate90 acceptance preparation

This suite is staged for the real signed 0.1.54/build90 APK. `meta.json` is deliberately absent until the native binary is built and sealed. Both planning and download contracts reject missing metadata, another package/version, baseline89's hash, a mutable source-commit label, and an APK URL outside the pinned public repository/file. The registered workflow filename remains `verify-capital-candidate-89.yml`; dispatch it from the reviewed branch after metadata is committed. It has no push trigger and no publication permissions.

The sole upgrade baseline is published, user-confirmed 0.1.53/build89: SHA256 `f2309b850e9b953e6d94cbf9b63c8a6e4d6b01af570d512155a15401ee15017d`, 82,248,242 bytes. The standard binary verifier additionally checks the original signing certificate, package and versions. Each emulator independently checks the installed base APK's complete bytes before and after upgrade.

`all` schedules twelve real Android cases:

* Six API30/35/36 × saved `aurora`/`moss` upgrades preserve appearance storage, address UUID, manual queue/reminders and dated offline cache. They exercise themed cancel/back/discard, validation, guarded delete/cancel, manual queue edit and clean start. Historical `moss` storage renders the current dark fallback and remains stored unchanged.
* Three Popivka cases require both published89 and candidate90 to render today's real official intervals. The independent observer preserves fetched HTML and hashes. The saved-correct-queue regression fixture contains no schedule or intervals. After IPv4 and IPv6 app-UID isolation, force-stop freezes the last successful candidate cache; offline restart must preserve that exact cache and timestamp.
* Three historical-hint cases use frozen Poltava `UA-53-capital-5` (Чумаківська, будинок1) and the same independent source plan on API30/35/36. Ordinary app controls perform city/street/house selection and save. No address or queue is injected or typed into queue fields. A proposal must leave the queue unassigned until the explicit button click. Visible warnings, original17Oct date, literal source house and source link must belong to the exact on-screen candidate/notice. After selection, public origin, original publication/snapshot, observed/expiry dates, explicit confirmation time and UUID survive offline refresh/restart; reminders remain off.

The two regression suites seed clearly marked disposable emulator retention fixtures only. Their successes contribute zero address-lookup coverage. Historical UI attempts also contribute zero official automatic coverage.

Historical planning reads the actual public `public-evidence/manifest.json`; it does not substitute the staged draft. First publish the reviewed compatible manifest through the owner's release process. Planning verifies the existing baseline/holdout hashes, uniquely matching literal house, reviewed `Elvis129/prosvitlo-addresses-db` Git/rawSHA pin, original publication commit/date/file touch, and exact original GPV JSON projection. Source eligibility is seven-to180days old with a current observation; re-reading never resets the source date. Actual postal context may contain exactly17ASCII digits with optional `UA`; acceptance compares this representation without replacing app data. If a frozen positive case disappears, the plan fails instead of choosing an invented address.

All observed SQLite captures retain original sidecars and hashes. `mode=ro` queries run on a disposable whole-directory analysis copy because SQLite can update even a read-only WAL reader's local shared-memory sidecar. No original capture bytes are changed. A fresh pull may retry only the two known read-only hot-journal/malformed-capture errors. There is no journal removal, immutable bypass or repair. Workflow artifacts retain screenshots, Android trees, every original capture, official/source observations and exact binary proof for90days. A failed product attempt must remain a failure.

Preparation tests are runnable without an SDK:

```sh
python3 .github/qa/native90/test-contract.py
python3 .github/qa/native90/test-tap-target.py
python3 .github/qa/native90/test-selection.py
python3 .github/qa/native90/test-historical-screen.py
python3 .github/qa/test-historical-hint-audit.py
python3 .github/qa/native90/popivka/test-source.py
python3 .github/qa/native90/popivka/test-screen.py
```

These controls validate the acceptance machinery. They are not an Android pass or a release approval. No candidate90 Android result exists until the real APK, public manifest, and emulator runs are available.
