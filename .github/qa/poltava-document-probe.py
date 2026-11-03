"""Read-only ordinary Chromium proof for a current official Poltava GPV PDF.
No queue inference, challenge interaction, anonymous state export or publication.
"""
import datetime as dt
import hashlib
import io
import json
import re
import time
import urllib.parse
from html.parser import HTMLParser
from pathlib import Path

MAX_BODY = 16 * 1024 * 1024
HOST = 'www.poe.pl.ua'
INDEX = 'https://www.poe.pl.ua/disconnection/hrafik-pohodynnoho-vidkliuchennia-elektroenerhii/'


def official_pdf(url):
    p = urllib.parse.urlsplit(url)
    return p.scheme == 'https' and p.hostname == HOST and not p.username and not p.password and not p.fragment and not p.query and p.path.startswith('/wp-content/uploads/') and p.path.lower().endswith('.pdf')


class ActivePDFs(HTMLParser):
    def __init__(self, base=INDEX):
        super().__init__(convert_charrefs=True)
        self.base = base; self.links = []; self.stack = []; self.heading = None; self.heading_text = []; self.archived_section = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        archive = bool(re.search(r'архів|архив|archive|history', attrs.get('class', '') + ' ' + attrs.get('id', ''), re.I))
        if tag not in ['area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr']:
            self.stack.append((tag, archive))
        if re.fullmatch(r'h[1-6]', tag): self.heading = tag; self.heading_text = []
        if tag == 'a' and attrs.get('href') and not self.archived_section and not any(a for _, a in self.stack):
            url = urllib.parse.urljoin(self.base, attrs['href'])
            if official_pdf(url) and url not in self.links: self.links.append(url)

    def handle_data(self, value):
        if self.heading: self.heading_text.append(value)

    def handle_endtag(self, tag):
        if tag == self.heading:
            self.archived_section = bool(re.search(r'архів|архив|archive|history', ' '.join(self.heading_text), re.I)); self.heading = None
        for i in range(len(self.stack)-1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]; break


def period(text, now=None):
    # Require the explicit source period; path/year and article age are insufficient.
    now = now or dt.datetime.now(dt.timezone.utc)
    compact = re.sub(r'\s+', ' ', text)
    m = re.search(r'(?:з|на період з)\s*(\d{2})[./](\d{2})[./](20\d{2})(?:\s*(?:р(?:оку|\.)?)?\s*)(?:по|до|[-–])\s*(\d{2})[./](\d{2})[./](20\d{2})', compact, re.I)
    if not m: return {'status': 'explicit_period_missing'}
    try:
        a = dt.datetime(int(m[3]), int(m[2]), int(m[1]), tzinfo=dt.timezone.utc)
        b = dt.datetime(int(m[6]), int(m[5]), int(m[4]), tzinfo=dt.timezone.utc)
    except ValueError: return {'status': 'invalid_period'}
    current = a <= now < b
    return {'status': 'current' if current else 'not_current', 'from': a.isoformat(), 'until': b.isoformat()}


def challenge(text):
    return bool(re.search(r'just a moment|verify (?:you are|that you are) human|checking your browser|підтверд[іи]ть.*людин|access denied', text, re.I))


def main():
    from playwright.sync_api import sync_playwright
    import pdfplumber
    request = json.loads(Path('.github/qa/poltava-document-request.json').read_text())
    if request.get('indexUrl') != INDEX: raise ValueError('unreviewed_index')
    lead = request['reviewedDocumentLead']
    if not official_pdf(lead): raise ValueError('unreviewed_document_host')
    out = Path('poltava-document-evidence'); out.mkdir(exist_ok=True)
    report = {'schemaVersion': 1, 'checkedAt': int(time.time()*1000), 'method': 'ordinary-Chromium-public-source-probe-only', 'operatorId': 'poltava', 'indexUrl': INDEX, 'queueClaims': 0, 'documents': []}
    def save(name, raw):
        (out/name).write_bytes(raw)
        return {'file': name, 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(locale='uk-UA')
        page = context.new_page()
        active = []
        try:
            response = page.goto(INDEX, wait_until='domcontentloaded', timeout=45000)
            page.wait_for_timeout(1500)
            raw = page.content().encode(); text = page.locator('body').inner_text(timeout=5000)
            report['index'] = {'status': response.status if response else None, 'finalUrl': page.url, 'challenge': challenge(text), **save('official-index.html', raw)}
            page.screenshot(path=str(out/'official-index.png'), full_page=False)
            if report['index']['challenge']:
                report['constraint'] = 'official_index_challenge_no_interaction'
            elif response and response.ok:
                parser = ActivePDFs(page.url); parser.feed(raw.decode()); active = parser.links[:6]
        except Exception as error:
            report['index'] = {'error': type(error).__name__}
        report['activeOfficialPDFLinks'] = active
        # Direct reviewed public link is a diagnostic candidate only. Absence on
        # the current official index cannot be relabelled as an active source.
        candidates = list(dict.fromkeys(active + [lead]))
        if not report.get('constraint'):
            for i, url in enumerate(candidates):
                item = {'url': url, 'activeOnOfficialIndex': url in active, 'promotion': 'unpromoted_source_proof_only'}
                try:
                    response = context.request.get(url, timeout=45000, headers={'Referer': INDEX})
                    item['status'] = response.status
                    length = response.headers.get('content-length')
                    if length and int(length) > MAX_BODY: raise ValueError('public_document_size_limit')
                    raw = response.body()
                    if len(raw) > MAX_BODY: raise ValueError('public_document_size_limit')
                    item.update(save(f'document-{i}.pdf' if raw.startswith(b'%PDF') else f'document-{i}-error.html', raw))
                    if not response.ok: item['constraint'] = 'official_document_http_failure'
                    elif not raw.startswith(b'%PDF'): item['constraint'] = 'official_response_not_pdf'
                    else:
                        with pdfplumber.open(io.BytesIO(raw)) as pdf:
                            first = '\n'.join(page.extract_text() or '' for page in pdf.pages[:2])
                            item['pages'] = len(pdf.pages); item['sourcePeriod'] = period(first)
                            item['isGPV'] = bool(re.search(r'графік\s+погодинн', first, re.I))
                            item['textProof'] = save(f'document-{i}-first-pages.txt', first.encode())
                except Exception as error: item['error'] = type(error).__name__
                report['documents'].append(item)
        context.close(); browser.close()
    (out/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'index': report.get('index', {}).get('status'), 'activeLinks': len(active), 'documents': [{'status':d.get('status'), 'period':d.get('sourcePeriod'), 'active':d['activeOnOfficialIndex']} for d in report['documents']], 'queueClaims':0}))

if __name__ == '__main__': main()
