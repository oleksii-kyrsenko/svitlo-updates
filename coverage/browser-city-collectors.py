"""Ordinary-browser city directory collection and official protocol research.

Only anonymous public source pages are visited. Chromium's normal public session
is used without stealth, CAPTCHA interaction, credentials or subscriber input.
The Chernihiv mode collects public protocol evidence, not guessed queue facts.
"""
import argparse
import hashlib
import importlib.util
import json
import re
import time
import unicodedata
import urllib.parse
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).resolve().parent
MAX_PUBLIC_BODY = 8_000_000


def module(filename, name):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


BROWSER = module('browser-official.py', 'browser_city_transport')
BATCH = module('batch-a.py', 'browser_city_public_roster')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def clean(value):
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def locality(value):
    value = unicodedata.normalize('NFKC', clean(value)).casefold()
    return re.sub(r'^(?:(?:м|с)\.\s*|(?:місто|село|селище)\s+)', '', value)


def house_key(value):
    value = unicodedata.normalize('NFKC', clean(value)).casefold()
    value = re.sub(r'[\s№]', '', value)
    value = value.translate(str.maketrans({'a': 'а', 'c': 'с', 'e': 'е', 'o': 'о', 'p': 'р', 'x': 'х'}))
    return re.sub(r'(\d)[‐‑‒–—-](?=[а-яіїєґ]$)', r'\1', value)


def literal_house(value):
    value = clean(value)
    return value if re.fullmatch(r'\d{1,4}(?:[- ]?[А-Яа-яІіЇїЄєҐґA-Za-z])?(?:/\d{1,4}[А-Яа-яІіЇїЄєҐґA-Za-z]?)?', value) else None


class DirectoryPage(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.select = None
        self.option = None
        self.options = []
        self.base = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a' and attrs.get('href'):
            self.links.append(attrs['href'])
        if tag == 'meta' and attrs.get('property') == 'og:url':
            self.base = attrs.get('content')
        if tag == 'select':
            self.select = attrs.get('name')
        if tag == 'option' and self.select == 'diln':
            self.option = {'id': attrs.get('value'), 'name': '', 'disabled': 'disabled' in attrs}

    def handle_data(self, value):
        if self.option is not None:
            self.option['name'] += value

    def handle_endtag(self, tag):
        if tag == 'option' and self.option is not None:
            if not self.option['disabled'] and re.fullmatch(r'[1-9]\d{0,3}', str(self.option['id'] or '')):
                self.options.append({'id': self.option['id'], 'name': clean(self.option['name'])})
            self.option = None
        if tag == 'select':
            self.select = None


def parse_directory(body):
    value = DirectoryPage()
    value.feed(body)
    return value


def sourced_target(operator, target=None):
    config = json.loads((HERE / 'sources.json').read_text())
    source = next((row for row in config['operators'] if row['id'] == operator), None)
    if not source:
        raise ValueError('unknown_source_operator')
    directory = json.loads((HERE / 'capital-geography.json').read_text())
    targets = [c for c in directory['cities'] if c['regionId'] in source['regionIds']]
    if len(targets) != 1 or not targets[0].get('community'):
        raise ValueError('verified_capital_context_required')
    geo = targets[0]
    if target and locality(target) != locality(geo['settlement']):
        raise ValueError('requested_city_differs_from_sourced_capital')
    return source, geo


def official_url(url, source):
    return BROWSER.same_official_host(url, source)


def branch_link(body, source):
    parsed = parse_directory(body)
    links = [urllib.parse.urljoin(source, href) for href in parsed.links]
    found = list(dict.fromkeys(url for url in links if official_url(url, source) and
                              re.fullmatch(r'/shutdowns-search/?', urllib.parse.urlsplit(url).path)))
    if len(found) != 1:
        raise ValueError('official_city_directory_link_not_unique')
    return found[0]


def branch_for_target(body, source, geo):
    parsed = parse_directory(body)
    matches = [row for row in parsed.options if locality(row['name']) == locality(geo['settlement'])]
    if len(matches) != 1:
        raise ValueError('official_city_branch_not_unique')
    if not official_url(parsed.base, source) or not re.fullmatch(r'/shutdowns-search/?', urllib.parse.urlsplit(parsed.base).path):
        raise ValueError('official_directory_base_not_confirmed')
    return matches[0], parsed.base.rstrip('/') + '/' + matches[0]['id'] + '/'


def roster_claims(body, branch, geo):
    result = {}
    for item in BATCH.parse_chernivtsi(body, branch):
        if locality(item['settlement']) != locality(geo['settlement']):
            continue
        house = literal_house(item['house'])
        if not house or not clean(item['street']):
            continue
        key = (clean(item['street']), house_key(house))
        group = result.setdefault(key, {'street': clean(item['street']), 'house': house, 'queues': set()})
        q = str(item.get('queue', ''))
        group['queues'].add(q if re.fullmatch(r'[1-9]\d?(?:\.[12])?', q) else None)
    if not result:
        raise ValueError('target_city_has_no_literal_addresses')
    return result


def compare_rosters(first, second, geo, url, branch, observed_at):
    """A second actual source read must corroborate every published house."""
    rows, observations, conflicts = [], [], 0
    for key in sorted(set(first) | set(second)):
        a, b = first.get(key), second.get(key)
        item = b or a
        observation = {'regionId': geo['regionId'], 'settlement': geo['settlement'],
                       'community': geo['community'], 'street': item['street'], 'house': item['house'],
                       'checkedAt': observed_at, 'expiresAt': observed_at + 86400000}
        observations.append(observation)
        if not a or not b or len(a['queues']) != 1 or a['queues'] != b['queues'] or None in b['queues']:
            conflicts += 1
            continue
        queue = next(iter(b['queues']))
        row = BATCH.record('chernivtsi', geo['regionId'], geo['settlement'], geo['community'],
                           item['street'], item['house'], queue, url, observed_at)
        if row:
            identity = digest((str(branch) + '|' + geo['settlement'] + '|' + item['street']).encode())[:24]
            row['officialCityId'] = 'chernivtsi:' + str(branch) + ':' + identity
            rows.append(row)
    return rows, observations, conflicts


def collect_chernivtsi(page, context, source, geo, out, request_limit):
    http = BROWSER.BrowserHTTP(page, context, source, request_limit, evidence_directory=out)
    main = http.text(source)
    directory_url = branch_link(main, source)
    directory = http.text(directory_url)
    branch, url = branch_for_target(directory, source, geo)
    first_body = http.text(url)
    first = roster_claims(first_body, branch['id'], geo)
    second_body = http.text(url)
    checked = int(time.time() * 1000)
    second = roster_claims(second_body, branch['id'], geo)
    rows, observations, conflicts = compare_rosters(first, second, geo, url, branch['id'], checked)
    report = {'sourceDirectoryUrl': directory_url, 'sourceRosterUrl': url, 'sourceBranch': branch['id'],
              'firstReadHouses': len(first), 'secondReadHouses': len(second), 'records': len(rows),
              'unconfirmedOrChangedHouses': conflicts, 'requests': http.trace,
              'method': 'two-actual-official-public-roster-reads-with-exact-city-and-house-consensus',
              'cityCrawl': {'targetCity': geo['settlement'], 'status': 'complete-source-city-branch',
                            'dictionaryComplete': True, 'sourceBranchDiscoveredFromOfficialSelector': True}}
    if not rows and not observations:
        raise ValueError('no_verified_public_observations')
    packet = {'schemaVersion': 1, 'operatorId': 'chernivtsi', 'generatedAt': checked,
              'expiresAt': checked + 86400000, 'records': rows, 'observedHouses': observations}
    path = out / 'normalized-candidates.json'
    path.write_text(json.dumps(packet, ensure_ascii=False, separators=(',', ':')) + '\n')
    report['candidateBundle'] = {'path': path.name, 'sha256': digest(path.read_bytes())}
    return report


def origin(url):
    parsed = urllib.parse.urlsplit(url)
    return parsed.scheme + '://' + parsed.netloc


def research_chernihiv(page, source, out, script_responses):
    """Retain anonymous public source/iframe/static-code authority chain.

    No address/account endpoint is called until its source codec and scope have
    been independently reviewed. In particular list_acc is a lead, not permission
    to publish subscriber identifiers or infer queues.
    """
    root = origin(source)
    frames = page.locator('iframe[src]').evaluate_all('(items)=>items.map(item=>item.src)')
    allowed = {root}
    linked = []
    for url in frames:
        p = urllib.parse.urlsplit(url)
        # Only source-linked operator-owned frame domains are protocol evidence.
        if p.scheme == 'https' and not p.username and not p.password and p.hostname and \
                (p.hostname.endswith('.chernihivoblenergo.com.ua') or p.hostname.endswith('.energy.cn.ua')):
            allowed.add(origin(url)); linked.append(url)
    html = page.content().encode()
    if len(html) <= MAX_PUBLIC_BODY:
        path = out / 'official-parent.html'; path.write_bytes(html)
        parent = {'path': path.name, 'sha256': digest(html), 'sourceUrl': source}
    else:
        raise ValueError('official_parent_document_too_large')
    scripts, total = [], 0
    for response in script_responses:
        url = response.url
        p = urllib.parse.urlsplit(url)
        if origin(url) not in allowed or not p.path.endswith('.js') or response.status != 200:
            continue
        if not re.search(r'/(?:blackouts|interruptions|custom|global)\.js$', p.path):
            continue
        raw = response.body()
        if len(raw) > 2000000 or total + len(raw) > 8000000:
            continue
        total += len(raw); path = out / ('public-script-' + digest(raw) + '.js'); path.write_bytes(raw)
        text = raw.decode('utf8', 'replace')
        leads = [line.strip()[:800] for line in text.splitlines() if re.search(r'list_acc|\$\.ajax|fetch\(|url\s*:|queue|ГПВ', line, re.I)][:60]
        scripts.append({'sourceUrl': url, 'path': path.name, 'sha256': digest(raw), 'bytes': len(raw),
                        'authorityParent': parent, 'sourceLinkedFrame': next((f for f in linked if origin(f) == origin(url)), None),
                        'protocolLeadsForReview': leads})
    return {'status': 'official-public-protocol-evidence-only', 'queueIntegrationVerified': False,
            'records': 0, 'officialParent': parent, 'sourceLinkedFrames': linked, 'publicScripts': scripts,
            'constraint': 'address-api-codec-and-public-scope-require-independent-review-before-collection'}


def run(operators, output, request_limit=20, target_city=None, playwright_factory=None):
    if not operators or len(operators) != len(set(operators)) or any(o not in ('chernivtsi', 'chernihiv') for o in operators):
        raise ValueError('unknown_browser_city_operator')
    if not 4 <= request_limit <= 120:
        raise ValueError('request_limit_must_allow_two_actual_roster_reads')
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    if playwright_factory is None:
        from playwright.sync_api import sync_playwright
        playwright_factory = sync_playwright
    report = {'schemaVersion': 1, 'method': 'ordinary-chromium-official-city-sources',
              'queueCoverageClaimed': False, 'startedAt': int(time.time() * 1000), 'operators': []}
    with playwright_factory() as engine:
        browser = engine.chromium.launch()
        try:
            for operator in operators:
                entry, geo = sourced_target(operator, target_city if len(operators) == 1 else None)
                source = entry['sourceUrl']; out = output / operator; out.mkdir(exist_ok=True)
                # A failed fresh run cannot leave an old candidate masquerading
                # as newly collected data in a reused output directory.
                previous_candidate=out/'normalized-candidates.json'
                if previous_candidate.exists():previous_candidate.unlink()
                context = browser.new_context(locale='uk-UA', viewport={'width': 1280, 'height': 900}, accept_downloads=False)
                page = context.new_page(); scripts = []
                page.on('response', lambda response: scripts.append(response) if len(scripts) < 200 and
                        'javascript' in response.headers.get('content-type', '') else None)
                item = {'operatorId': operator, 'sourceUrl': source, 'targetCity': geo['settlement'],
                        'checkedAt': int(time.time() * 1000), 'status': 'not_visited', 'queueIntegrationVerified': False}
                try:
                    from request_budget import throttle
                    throttle(source); response = page.goto(source, wait_until='domcontentloaded', timeout=45000)
                    page.wait_for_timeout(5000)
                    if not official_url(page.url, source):
                        raise BROWSER.SourceStop('official-source-redirected-to-another-host')
                    if reason := BROWSER.visible_block(page):
                        raise BROWSER.SourceStop(reason)
                    if not response or response.status >= 400:
                        raise BROWSER.SourceStop('official-document-unavailable')
                    item.update(status='public-page-rendered', navigationStatus=response.status, title=page.title())
                    if operator == 'chernivtsi':
                        item['collection'] = collect_chernivtsi(page, context, source, geo, out, request_limit)
                        item['status'] = 'official-city-candidates-collected'
                    else:
                        item['research'] = research_chernihiv(page, source, out, scripts)
                        item['status'] = 'official-protocol-artifacts-retained'
                except Exception as error:
                    item.update(status='stopped-' + error.reason if isinstance(error, BROWSER.SourceStop) else 'source-error',
                                error=error.reason if isinstance(error, BROWSER.SourceStop) else type(error).__name__)
                finally:
                    item['pageEvidence'] = BROWSER.page_artifacts(page, out)
                    context.close(); report['operators'].append(item)
                    (out / 'report.json').write_text(json.dumps(item, ensure_ascii=False, indent=2) + '\n')
                    report['finishedAt'] = int(time.time() * 1000)
                    (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
                    print(json.dumps({'operatorId': operator, 'status': item['status'],
                                      'records': item.get('collection', {}).get('records', 0)}), flush=True)
        finally:
            browser.close()
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--operators', default='chernivtsi,chernihiv')
    p.add_argument('--operator', choices=('chernivtsi', 'chernihiv'))
    p.add_argument('--target-city'); p.add_argument('--request-limit', type=int, default=20)
    p.add_argument('--output', required=True)
    args = p.parse_args()
    run([args.operator] if args.operator else [v.strip() for v in args.operators.split(',') if v.strip()],
        args.output, args.request_limit, args.target_city)
