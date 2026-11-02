"""Bounded ordinary Chromium research of official public electricity sources.

No stealth options, CAPTCHA solving, authenticated sessions or subscriber input.
Page availability and browser access are never reported as queue coverage.
Normalized Vinnytsia candidates still require the normal publisher/verifier gates.
"""
import argparse
import hashlib
import importlib.util
import json
import re
import time
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_OPERATORS = ('vinnytsia', 'sumy', 'poltava', 'chernihiv', 'kherson')
MAX_BODY = 8_000_000
MAX_ARTIFACT = 2_000_000


class SourceStop(RuntimeError):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def https(url):
    try:
        parsed = urllib.parse.urlsplit(url)
        return parsed.scheme == 'https' and bool(parsed.hostname) and not parsed.username and not parsed.password and not parsed.fragment
    except (TypeError, ValueError):
        return False


def same_official_host(url, source):
    if not https(url):
        return False
    host = urllib.parse.urlsplit(url).hostname
    expected = urllib.parse.urlsplit(source).hostname
    return host.removeprefix('www.') == expected.removeprefix('www.')


def raw_block(body):
    """Only explicit interstitials, not a normal site's CAPTCHA script reference."""
    text = body.lower()
    if ('cf-chl-' in text or '_incapsula_resource' in text) and re.search(r'just a moment|verify (?:you are|that you)|checking your browser|access denied|incident id', text):
        return 'source-protection-interstitial'
    if re.search(r'<title[^>]*>\s*(?:access denied|403 forbidden|please verify|attention required)', text):
        return 'source-protection-interstitial'
    return None


def visible_block(page):
    # Do not click a challenge, submit credentials, change fingerprint or retry
    # through another network. An ordinary page may include an invisible CAPTCHA
    # library: only a visible control/interstitial is a stop condition here.
    for selector in ('iframe[src*="recaptcha"]', 'iframe[src*="hcaptcha"]',
                     'iframe[src*="challenges.cloudflare.com"]', '.cf-turnstile',
                     '[data-captcha]', '#captcha', '[name="captcha"]'):
        items = page.locator(selector)
        for index in range(min(items.count(), 10)):
            if items.nth(index).is_visible():
                return 'visible-captcha-or-turnstile'
    for selector in ('input[type="password"]',):
        items = page.locator(selector)
        for index in range(min(items.count(), 10)):
            if items.nth(index).is_visible():
                return 'visible-login-required'
    try:
        return raw_block(page.content())
    except Exception:
        return None


def request_summary(response):
    """No cookies, tokens, request bodies or personal payloads enter diagnostics."""
    parsed = urllib.parse.urlsplit(response.url)
    return {'host': parsed.hostname, 'path': parsed.path, 'status': response.status,
            'contentType': response.headers.get('content-type', '').split(';')[0]}


def page_artifacts(page, directory, prefix='page'):
    result = {}
    try:
        path = directory / (prefix + '.png')
        page.screenshot(path=str(path), full_page=False, timeout=10000)
        result['screenshot'] = {'path': path.name, 'sha256': sha(path.read_bytes())}
    except Exception as error:
        result['screenshotError'] = type(error).__name__
    try:
        body = page.content().encode()
        # Login/challenge pages and raw Drupal tokens are not a public-data
        # snapshot. Store only a bounded text rendering, never cookies/storage.
        text = page.locator('body').inner_text(timeout=2000).encode()
        if len(text) <= MAX_ARTIFACT:
            path = directory / (prefix + '.txt')
            path.write_bytes(text)
            result['visibleText'] = {'path': path.name, 'sha256': sha(text)}
        result['renderedHtmlSha256'] = sha(body)
        result['renderedBytes'] = len(body)
    except Exception as error:
        result['textError'] = type(error).__name__
    return result


class BrowserHTTP:
    """Existing public Drupal collector over the browser's ordinary session.

    The first document is the page just navigated by Chromium. Later public
    AJAX form requests reuse only that fresh anonymous browser context. The
    adapter never obtains a token outside the source's own form lifecycle.
    """
    def __init__(self, page, context, source, limit=60, evidence_directory=None):
        if not same_official_host(page.url, source):
            raise SourceStop('official-source-redirected-to-another-host')
        self.page, self.context, self.source = page, context, source
        self.limit, self.calls, self.trace = limit, 0, []
        self.deadline, self.first_document = time.monotonic() + 480, True
        self.evidence_directory = Path(evidence_directory) if evidence_directory else None
        self.evidence_bytes = 0

    def remember_public_body(self, body, event, *, rendered=False):
        if self.evidence_directory is None:
            return
        raw=body.encode()
        if len(raw)>MAX_ARTIFACT or self.evidence_bytes+len(raw)>16*1024*1024:
            event['originalEvidenceConstraint']='bounded-source-evidence-limit'
            return
        directory=self.evidence_directory/'raw';directory.mkdir(exist_ok=True)
        path=directory/(sha(raw)+'.txt')
        if not path.exists():
            path.write_bytes(raw);self.evidence_bytes+=len(raw)
        event['original']={'path':'raw/'+path.name,'sha256':sha(raw),'kind':'rendered-public-document' if rendered else 'ordinary-browser-fetch-response'}

    def text(self, url, fields=None, *, ajax=False, referer=None, accepted=()):
        if not same_official_host(url, self.source):
            raise SourceStop('cross-host-public-form-request-refused')
        if self.calls >= self.limit or time.monotonic() >= self.deadline:
            raise SourceStop('request-budget')
        reason = visible_block(self.page)
        if reason:
            raise SourceStop(reason)
        from request_budget import throttle
        throttle(url)
        self.calls += 1
        event = {'path': urllib.parse.urlsplit(url).path, 'method': 'POST' if fields is not None else 'GET',
                 'checkedAt': int(time.time() * 1000)}
        try:
            if self.first_document and fields is None and url.rstrip('/') == self.source.rstrip('/'):
                self.first_document = False
                body = self.page.content()
                event.update(status=200, bytes=len(body.encode()), sha256=sha(body.encode()), transport='rendered-public-page')
                self.remember_public_body(body,event,rendered=True)
                return body
            self.first_document = False
            headers = {'Accept': 'application/json,text/html', 'Accept-Language': 'uk'}
            if ajax:
                headers['X-Requested-With'] = 'XMLHttpRequest'
            if referer:
                if not same_official_host(referer, self.source):
                    raise SourceStop('cross-host-referer-refused')
                headers['Referer'] = referer
            if fields is not None:
                # Only address selection and source-provided Drupal state are
                # expected. Refuse any connection/account/user credential input.
                if ('search_type' in fields and str(fields['search_type'])!='0') or any(re.search(r'account|abon|eic|password|login|customer|subscriber', str(key), re.I) for key in fields):
                    raise SourceStop('subscriber-or-credential-input-refused')
                headers['Content-Type'] = 'application/x-www-form-urlencoded;charset=UTF-8'
            value = self.page.evaluate("""async ({url,method,headers,body,limit}) => {
                const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),25000);
                try {
                    const response=await fetch(url,{method,headers,...(body===null?{}:{body}),
                        credentials:'same-origin',redirect:'manual',signal:controller.signal});
                    if(response.type==='opaqueredirect')return {status:0,url,redirectRefused:true};
                    if(Number(response.headers.get('content-length'))>limit)throw Error('source-response-limit');
                    const reader=response.body.getReader(),parts=[];let size=0;
                    try {
                        while(true){const {done,value}=await reader.read();if(done)break;
                            size+=value.length;if(size>limit){controller.abort();throw Error('source-response-limit');}parts.push(value);}
                    } finally {reader.releaseLock();}
                    const bytes=new Uint8Array(size);let offset=0;for(const part of parts){bytes.set(part,offset);offset+=part.length;}
                    return {status:response.status,url:response.url,bytes:size,body:new TextDecoder('utf-8').decode(bytes)};
                } finally {clearTimeout(timer);}
            }""", {'url': url, 'method': 'POST' if fields is not None else 'GET',
                     'headers': headers, 'body': urllib.parse.urlencode(fields) if fields is not None else None, 'limit': MAX_BODY})
            if value.get('redirectRefused'):
                raise SourceStop('public-form-redirect-refused')
            if not same_official_host(value.get('url'), self.source):
                raise SourceStop('official-form-redirected-to-another-host')
            body = value['body']
            raw = body.encode()
            if value.get('bytes', len(raw)) > MAX_BODY or len(raw) > MAX_BODY:
                raise SourceStop('source-response-limit')
            event.update(status=value['status'], bytes=value.get('bytes', len(raw)), sha256=sha(raw), transport='ordinary-chromium-fetch')
            if reason := raw_block(body):
                raise SourceStop(reason)
            if not 200 <= value['status'] < 300 and value['status'] not in accepted:
                raise SourceStop('official-http-' + str(value['status']))
            self.remember_public_body(body,event)
            return body
        except Exception as error:
            event['error'] = error.reason if isinstance(error, SourceStop) else type(error).__name__
            raise
        finally:
            self.trace.append(event)

    def json(self, url, fields=None, **options):
        return json.loads(self.text(url, fields, **options))


def load_forms():
    spec = importlib.util.spec_from_file_location('browser_public_city_forms', HERE / 'collect-city-forms.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def collect_vinnytsia(page, context, source, directory, request_limit, target_city=None, state_path=None, bundle_path=None):
    forms = load_forms()
    data = json.loads((HERE / 'capital-geography.json').read_text())
    operator = next(r for r in json.loads((HERE / 'sources.json').read_text())['operators'] if r['id'] == 'vinnytsia')
    targets = [c for c in data['cities'] if c['regionId'] in operator['regionIds']]
    if len(targets) != 1:
        raise SourceStop('verified-capital-geography-required')
    geo=targets[0]
    if target_city and forms.city_key(target_city)!=forms.city_key(geo['settlement']):
        raise SourceStop('requested-target-is-not-the-sourced-capital')
    saved=json.loads(Path(state_path).read_text()) if state_path and Path(state_path).exists() else {}
    if not isinstance(saved,dict):raise SourceStop('invalid-public-crawl-state')
    state=forms.scoped_state(saved,geo['settlement'],True)
    http=BrowserHTTP(page,context,source,request_limit,evidence_directory=directory)
    try:
        rows,observed,completed,errors,metadata=forms.vinnytsia(http,geo,state)
    except Exception as error:
        rows,observed,completed,metadata=[],[],[],{}
        errors=[{'stage':'browser-public-form','error':type(error).__name__,'reason':error.reason if isinstance(error,SourceStop) else 'official-public-form-codec-or-request-failed'}]
    finally:
        if state_path:
            path=Path(state_path);path.parent.mkdir(parents=True,exist_ok=True)
            temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(saved,ensure_ascii=False,indent=2)+'\n');temporary.replace(path)
    now = int(time.time() * 1000)
    output = {'records': len(rows), 'observedHouses': len(observed), 'errors': errors,
              'requests': http.trace, 'metadata': metadata, 'notIndependentUiCoverage': True}
    if http.trace and http.trace[-1].get('error'):output['stoppedReason']=http.trace[-1]['error']
    if rows or observed:
        # No signing here. Only the existing separately validated publisher may
        # promote official facts; a browser being reachable is insufficient.
        bundle = {'schemaVersion': 1, 'operatorId': operator['id'], 'generatedAt': now,
                  'expiresAt': max((r['expiresAt'] for r in rows), default=now + 86400000),
                  'records': rows, 'observedHouses': observed, 'completedStreetIds': completed}
        path = directory / 'normalized-candidates.json'
        path.write_text(json.dumps(bundle, ensure_ascii=False, separators=(',', ':')) + '\n')
        if bundle_path:
            destination=Path(bundle_path);destination.parent.mkdir(parents=True,exist_ok=True)
            if destination.resolve()!=path.resolve():destination.write_bytes(path.read_bytes())
        output['candidateBundle'] = {'path': path.name, 'sha256': sha(path.read_bytes())}
    return output


def run(operators, output, request_limit=60, collect=False, playwright_factory=None, target_city=None, state_directory=None, state_file=None, bundle_path=None):
    registry = json.loads((HERE / 'sources.json').read_text())
    sources = {r['id']: r for r in registry['operators']}
    if not operators or len(set(operators)) != len(operators) or any(o not in DEFAULT_OPERATORS for o in operators):
        raise ValueError('unknown-or-duplicate-browser-operator')
    if not 1 <= request_limit <= 120:
        raise ValueError('unbounded-browser-request-limit')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    if playwright_factory is None:
        from playwright.sync_api import sync_playwright
        playwright_factory = sync_playwright
    report = {'schemaVersion': 1, 'startedAt': int(time.time() * 1000), 'method': 'ordinary-chromium-public-source-research',
              'queueCoverageClaimed': False, 'operators': [],
              'policy': 'No CAPTCHA solving, stealth, authentication, subscriber queries or direct publication.'}
    with playwright_factory() as engine:
        browser = engine.chromium.launch()
        try:
            for operator_id in operators:
                source = sources[operator_id]['sourceUrl']
                if not https(source):
                    raise ValueError('official-source-requires-https')
                directory = output / operator_id
                directory.mkdir(exist_ok=True)
                context = browser.new_context(locale='uk-UA', viewport={'width': 1280, 'height': 900}, accept_downloads=False)
                page = context.new_page()
                trace = []
                page.on('response', lambda response: trace.append(request_summary(response)) if len(trace) < 150 else None)
                result = {'operatorId': operator_id, 'sourceUrl': source, 'checkedAt': int(time.time() * 1000),
                          'status': 'not-visited', 'queueIntegrationVerified': False}
                try:
                    from request_budget import throttle
                    throttle(source)
                    response = page.goto(source, wait_until='domcontentloaded', timeout=45000)
                    if not same_official_host(page.url, source):
                        raise SourceStop('official-source-redirected-to-another-host')
                    # Let the site's normal public JavaScript render. No click,
                    # challenge interaction or alternative identity is used.
                    page.wait_for_timeout(5000)
                    result.update(finalUrl=page.url, title=page.title(), navigationStatus=response.status if response else None)
                    reason = visible_block(page)
                    if reason:
                        raise SourceStop(reason)
                    body_text = page.locator('body').inner_text(timeout=3000).strip()
                    if not body_text:
                        result['status'] = 'empty-rendered-source'
                    elif response and response.status >= 400:
                        result['status'] = 'official-http-' + str(response.status)
                    else:
                        result['status'] = 'public-page-rendered-not-address-integration'
                    if collect and operator_id == 'vinnytsia' and result['status'] == 'public-page-rendered-not-address-integration':
                        state_path=state_file or (Path(state_directory)/(operator_id+'.json') if state_directory else None)
                        result['collection'] = collect_vinnytsia(page,context,source,directory,request_limit,target_city,state_path,bundle_path)
                        if result['collection'].get('stoppedReason'):result['status']='stopped-'+result['collection']['stoppedReason']
                    result['publicRequests'] = trace
                except Exception as error:
                    result.update(status='stopped-' + error.reason if isinstance(error, SourceStop) else 'browser-source-error',
                                  error=error.reason if isinstance(error, SourceStop) else type(error).__name__)
                finally:
                    result['artifacts'] = page_artifacts(page, directory)
                    result['publicRequests'] = trace
                    context.close()
                    report['operators'].append(result)
                    (directory / 'report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
                    report['finishedAt'] = int(time.time() * 1000)
                    (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
                    print(json.dumps({'operatorId': operator_id, 'status': result['status'], 'records': result.get('collection', {}).get('records', 0)}), flush=True)
        finally:
            browser.close()
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--operators',default=','.join(DEFAULT_OPERATORS))
    parser.add_argument('--operator',choices=DEFAULT_OPERATORS)
    parser.add_argument('--target-city')
    parser.add_argument('--state')
    parser.add_argument('--state-directory')
    parser.add_argument('--output', required=True)
    parser.add_argument('--request-limit', type=int, default=60)
    parser.add_argument('--collect', action='store_true')
    args = parser.parse_args()
    if args.operator:
        if args.operator!='vinnytsia':raise SystemExit('Only Vinnytsia has a browser-backed normalized collector; use --operators for source probes.')
        if not args.target_city:raise SystemExit('--target-city is required for a normalized browser collector')
        destination=Path(args.output);evidence=destination.parent/(destination.stem+'-browser-evidence')
        report=run([args.operator],evidence,args.request_limit,True,target_city=args.target_city,state_file=args.state,bundle_path=destination)
        Path(str(destination)+'.report.json').write_text(json.dumps(report['operators'][0],ensure_ascii=False,indent=2)+'\n')
        candidate=report['operators'][0].get('collection',{}).get('candidateBundle')
        if not candidate or not destination.exists() or sha(destination.read_bytes())!=candidate['sha256']:raise SystemExit(2)
    else:
        run([o.strip() for o in args.operators.split(',') if o.strip()],args.output,args.request_limit,args.collect,state_directory=args.state_directory)
