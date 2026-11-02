# Ordinary browser collection for blocked official sources

This is executable tooling preparation, not a successful browser run or a queue
coverage claim. Real Chromium runs are preserved by `official-browser.yml`.

`coverage/browser-official.py` visits the operator URL from the public registry
for Vinnytsia, Sumy, Poltava, Chernihiv and Kherson. It uses ordinary Chromium,
fresh anonymous contexts and the site's normal JavaScript. It does not change
user agent/fingerprint, solve CAPTCHA/Turnstile, enter credentials, obtain
subscriber identifiers, use a proxy alternative or publish application data.
A visible challenge/login or explicit protection response stops that source.
A rendered page is explicitly not an address integration.

For Vinnytsia only, the existing standalone public Drupal address collector can
run through actual same-origin Chromium `fetch` with the anonymous source form's
own current state. All street/house IDs are discovered from official address
responses. A matching single queue and the selected-address echo are required
by that collector; no test address or queue is embedded here. The source's
public address cursor persists separately from browser state. Cookies and local
storage are never saved.

## Commands

Probe all five sources; optionally collect Vinnytsia candidates:

```sh
python3 coverage/browser-official.py \
  --operators vinnytsia,sumy,poltava,chernihiv,kherson \
  --request-limit 60 --collect --state-directory browser-source-state \
  --output browser-source-evidence
```

Use the normalized single-operator collector contract:

```sh
python3 coverage/browser-official.py \
  --operator vinnytsia --target-city 'Вінниця' \
  --request-limit 60 --state /tmp/vinnytsia-browser-cursor.json \
  --output /tmp/vinnytsia-browser.json
```

The latter exits2 when no new usable candidate bundle was obtained. An old output
file does not turn a failed fresh read into success. Both commands require the
free `playwright==1.56.0` Python package and its Chromium installation. The public
workflow installs these on GitHub's runner, leaving the Android build workspace
untouched.

## Evidence and promotion boundary

Reports retain source/status/time, public response path/status/type, bounded real
screenshots and visible text. They omit request bodies, cookies and headers.
Known Vinnytsia anonymous address/form response bodies are retained separately
under SHA256 names, with a distinction between a rendered public document and
an original Chromium-fetch response. Those public form originals may contain
short-lived, anonymous, source-generated Drupal form state. No account mode is
queried. Per-response evidence is limited to2MB and16MB per operator collection;
missing originals are an explicit evidence limit, never a fabricated source.

`normalized-candidates.json` contains only the existing normalized public fact
contract. It is **unsigned and unpromoted**. The browser workflow has read-only
repository permissions and uploads artifacts only. Root/source-side publisher
must inspect independent source evidence, validate all records, preserve original
checkedAt/expiresAt and pass the normal signature/publication gates before any
candidate reaches devices. A successful browser workflow job does not establish
coverage or successful queue lookup.

The six-hour workflow restores only public crawl cursors in Actions cache. Its
artifact records whether a source was protected, empty, failed or rendered, even
when no queue candidate could be extracted. No claim is made that plain HTTP
failures or CAPTCHA-protected sources were repaired by adding this workflow.
