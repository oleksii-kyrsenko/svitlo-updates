# Poltava and Kharkiv official source investigation — 2026-11-03

This is source research, not Android queue coverage. No queue fact has been
promoted from this investigation.

## Kharkiv: current official PDF is publicly readable

The registered official address page
`https://oblenergo.kharkiv.ua/uk/gaoinfo` returned HTTP200 at20:49UTC. It embeds
`https://pa.oblenergo.kharkiv.ua/frontend/web/index.php/uk/portal-application/disconnection-by-address`.
That anonymous form also returned200, but requires
`DisconnectionByAddressForm[captchaToken]` from Cloudflare Turnstile before its
address submission. No token acquisition, challenge interaction or form
submission was attempted.

Current29October–1November messages in the public operator-labelled channel
`https://t.me/s/kharkivenergy/2288` link an official-host PDF:

`https://oblenergo.kharkiv.ua/sites/default/files/pdf/Адреси%20та%20черги%2026-27.pdf`

Ordinary HTTPS in the workspace downloaded the PDF successfully at20:50:18UTC:
189984bytes, SHA256
`da7a484960696e8e9b349aeec0e63b22e2f15520fa38525ea7433ac4f23a2180`.
Its first-page title explicitly gives01.10.2026–01.04.2027; all9pages were read.
The web search fetcher returned403 for the same file; the actual ordinary HTTPS
result demonstrates that this source cannot simply be classified as universally
unavailable.

The current document mostly lists oblast localities, street descriptions and
named business connections. It does not establish the five frozen Kharkiv
residential house assignments. In particular, a literal occurrence of
**Римарська** belongs to **с.Колонтаїв**, not the Kharkiv control address. The many
**Кооперативна** entries belong to several oblast localities; these are not
interchangeable with the city of Kharkiv. **Нескорених**, **Велика Жихорська** and
**Людвіга Свободи** are absent as literal street names. No conclusion about a
whole city exemption follows from absence in this PDF.

A named business and its street/house identify that particular connection;
that is insufficient to assign every residential connection in the same house.
Likewise, bare streets or district descriptions do not provide an explicit
all-houses scope. These cases therefore abstain under the existing publication
contract. No artificial `усі будинки` quote was created.

Permanent originals, all-page PDF text/tables, request-status metadata and the
source-boundary report are in
`/workspace/library-files/capital-coverage-90/poltava-kharkiv-nov3/`.
`official-public-source-proof.zip` is341274bytes, SHA256
`37762ddaedd85f278f308bd3232db8706c486ae4a345d5593b9d80d05c65ce0f`.
The old2025Telegram attachment and old2025third-party PDF copies are not promoted.

## Poltava: concrete current PDF lead, transport still unresolved

The operator press-service article
`https://poltava.to/project/11187/` (25September2026) announces the current
01October2026–01April2027period. The current6October article
`https://pl.tram.news/ukr/news/city-news/a1259688-na-poltavshchini-do-pivnochi-vimikatimut-svitlo-za-hrafikami-jak-diznatisja-svoju-cherhu`
links this exact official PDF:

`https://www.poe.pl.ua/wp-content/uploads/2026/09/HPV_26_27-sajt.pdf`

Both the registered operator index and that PDF returned503 via ordinary
workspace HTTPS. Search-tool PDF fetch failed too. A filename containing26_27
or a news article's stated period is not a substitute for reading the document.
No data was inferred from older2025or spring2026copies.

A separate public, read-only Chromium proof workflow was added on the QA branch
atcommit`a7c4784`, with five source-boundary tests. It reads the live operator
index, ignores commented/archive anchors, records current active PDF links, and
separately marks the reviewed PDF lead when not confirmed on the live index.
A downloaded PDF must supply its own explicit current period. A challenge stops
interaction. The workflow never signs, promotes or invents queue data.

Workflow `.github/workflows/poltava-document-probe.yml`, initialrun41716757362.
Its result must be inspected before making any successful-access claim.

The actual ordinary Chromium run41716757362 completed successfully as a **probe**:
source index navigation and the direct current PDF request both timed out. It
obtained no active-index link, no PDF bytes and no queue fact. This is not a
successful integration or source read. The490-byte original artifact ZIP and its
report are retained under
`poltava-kharkiv-nov3/browser-41716757362/`; archive SHA256
`35fbe69df8dbc9de45f651d07a877d76e4b46c29ca6716049b0f526f7cb830e8`.
There was no CAPTCHA interaction or alternate network route. The official PDF
remains a concrete, unresolved current source lead, not a guessed queue list.
