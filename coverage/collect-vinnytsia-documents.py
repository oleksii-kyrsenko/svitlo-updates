"""Literal official Vinnytsia city house facts from the currently linked GPV PDF.

The municipal department has unruled, vertically centred queue labels. Only
separate text paragraphs with one unambiguous queue become candidates; ranges
and partial houses are never expanded. This is not a full city inventory.
"""
import argparse, hashlib, importlib.util, io, json, re, time, urllib.parse, urllib.request
from pathlib import Path
import pdfplumber
from city_crawl import city_key, request_limit
from source_utils import clean, record

_spec = importlib.util.spec_from_file_location('cherkasy_document_literals', Path(__file__).with_name('collect-cherkasy-documents.py'))
literal = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(literal)
INDEX = 'https://voe.com.ua/informatsiya-pro-cherhy-hrafika-pohodynnykh-vidklyuchen-hpv-1'

def period(text):
    return literal.period(re.sub(r'\bроку\b', '', text))

def current_document(html, now):
    html = re.sub(r'<!--.*?-->', '', html, flags=re.S)
    found = []
    for match in re.finditer(r'<div\s+class=["\']component-file__title["\'][^>]*>(.*?)</div>\s*<div\s+class=["\']component-file__btn["\'][^>]*>\s*<a\s+[^>]*href=["\']([^"\']+)', html, re.S):
        title, href = match.groups()
        if not re.search(r'\bГПВ\b', clean(title)): continue
        start, end = period(title)
        if not start <= now < end: continue
        url = urllib.parse.urljoin(INDEX, href)
        parts = urllib.parse.urlsplit(url)
        if parts.scheme != 'https' or parts.netloc != 'voe.com.ua' or not parts.path.endswith('.pdf') or parts.query or parts.fragment: raise ValueError('unexpected_document_authority')
        found.append({'url': url, 'title': clean(title), 'effectiveFrom': start, 'effectiveUntil': end})
    if len(found) != 1: raise ValueError('one_current_official_document_required')
    return found[0]

def paragraphs(words):
    """Return source text paragraphs and separately positioned queue labels.

    The actual PDF's municipal data column begins at x=43.8pt, its queue column
    ends at x=38pt. A14pt gap separates text paragraphs. An unexpected page
    width/column or competing queue at a paragraph boundary fails closed.
    """
    labels = [w for w in words if w['x1'] < 45 and re.fullmatch(r'[1-6]\.[12]', w['text'])]
    lines = []
    for word in sorted((w for w in words if w['x0'] >= 40), key=lambda w: (w['top'], w['x0'])):
        match = next((line for line in reversed(lines[-3:]) if abs(line['top'] - word['top']) <= 2), None)
        if match is None: lines.append({'top': word['top'], 'bottom': word['bottom'], 'words': [word]})
        else: match['words'].append(word); match['bottom'] = max(match['bottom'], word['bottom'])
    lines.sort(key=lambda line: line['top']); groups = []
    for line in lines:
        if not groups or line['top'] - groups[-1][-1]['top'] > 14: groups.append([])
        groups[-1].append(line)
    out = []
    for group in groups:
        top, bottom = group[0]['top'], group[-1]['bottom']
        queues = {w['text'] for w in labels if top <= (w['top'] + w['bottom']) / 2 <= bottom}
        if len(queues) != 1: continue
        # A paragraph whose neighbouring label has another queue is retained
        # only when that label lies outside the complete source text bounds.
        text = ' '.join(' '.join(w['text'] for w in sorted(line['words'], key=lambda w: w['x0'])) for line in group)
        out.append({'text': text, 'queue': next(iter(queues)), 'top': top, 'bottom': bottom})
    return out

def city_claims(raw, document):
    claims = []; excerpts = []; active = False; ended = False; seen = set()
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        if not 1 <= len(pdf.pages) <= 100: raise ValueError('unexpected_document_pages')
        heading = pdf.pages[0].extract_text() or ''
        if period(heading) != (document['effectiveFrom'], document['effectiveUntil']): raise ValueError('pdf_effective_period_mismatch')
        for number, page in enumerate(pdf.pages, 1):
            if not 590 <= page.width <= 600: raise ValueError('unexpected_document_geometry')
            words = page.extract_words(); text = page.extract_text() or ''
            start = re.search(r'СО\s*["«]\s*ВМЕМ\s*["»]', text)
            if start:
                if active or ended: raise ValueError('duplicate_municipal_department')
                active = True
            if not active: continue
            # The next named department is a genuine geography boundary,
            # including when it begins halfway down a page.
            departments = [w for w in words if w['text'].startswith('"ВЦЕМ') or w['text'].startswith('«ВЦЕМ')]
            cutoff = min((w['top'] - 2 for w in departments), default=page.height)
            scoped = [w for w in words if w['bottom'] <= cutoff]
            for paragraph in paragraphs(scoped):
                seen.add(paragraph['queue'])
                # Village/locality and non-city department rows are not city
                # evidence, even when administered by the municipal network.
                if re.search(r'(?<![\w.])(?:с|м|смт)\s*\.', paragraph['text']): continue
                values = parse_paragraph(paragraph, number, document)
                claims.extend(values); excerpts.append({**paragraph, 'page': number, 'claims': len(values)})
            if cutoff < page.height: ended = True; active = False; break
    if not ended or seen != {f'{a}.{b}' for a in range(1, 7) for b in [1, 2]}: raise ValueError('incomplete_municipal_queue_section')
    return claims, excerpts

def parse_paragraph(paragraph, page, document):
    text = paragraph['text']
    # A lane ordinal before its type is not a house of the preceding street.
    # Numbered lanes are deliberately omitted until their source name grammar
    # is supported; the marker has no known street type and cannot be promoted.
    text = re.sub(r'(?<![\w])\d+\s*(?:[-–]\s*й)?\s+(?:пров(?:улок)?\.?|проїзд)\s*', '; Номерований ', text, flags=re.I)
    # An initial of the next street is not a suffix of the preceding house.
    text = re.sub(r'(\d)\s+([А-ЯІЇЄҐA-Z])(?=\.)', r'\1; \2', text)
    # A suffixed numeric endpoint is still uncertain. Extend its veto to the
    # complete numeric interval; never create addresses by expanding it.
    text = re.sub(r'(\d+)\s*[-–—]\s*(\d+)\s*[А-Яа-яІіЇїЄєҐґ](?![\w])', r'\1-\2', text)
    values = literal.parse_cell({'page': page, 'text': text}, {**document, 'queue': paragraph['queue']})
    for value in values:
        value['houses'] = [h for h in value['houses'] if not re.search(r'[- ](?:й|я)$', h, re.I)]
        # Unqualified names can veto an explicit conflicting claim, but this
        # collector does not infer their street/lane type for a positive fact.
        if not value['kind']: value['queue'] = None
        value['excerpt'] = paragraph['text'][:2400]
    return [v for v in values if (v['houses'] or v.get('ranges')) and not re.search(r'\b(?:пров|вул|проїзд)\b', v['street'], re.I)]

def consolidate(claims, geography, checked_at, effective_until):
    # Reuse the already exercised literal/range/qualifier conflict policy;
    # its temporary records are remapped below before any output is written.
    old, observations, conflicts = literal.consolidate(claims, geography, checked_at, effective_until)
    expiry = min(checked_at + 86400000, effective_until); rows = []
    for item in old:
        row = record('vinnytsia', geography['regionId'], geography['settlement'], geography['community'], item['street'], item['houses'][0], item['queue'], item['sourceUrl'], checked_at)
        row.update(houses=item['houses'], expiresAt=expiry, quote=item['quote'].replace('Черкаські міські ЕМ', 'СО "ВМЕМ" Вінницяобленерго'), quoteType='official-document-excerpt')
        row['id'] = hashlib.sha256(('vinnytsia|' + item['id']).encode()).hexdigest()[:24]; rows.append(row)
    return rows, observations, conflicts

class HTTP:
    def __init__(self, limit, evidence=None): self.limit = limit; self.evidence = evidence; self.calls = 0; self.trace = []
    def get(self, url):
        if self.calls >= self.limit: raise ValueError('request_budget')
        from request_budget import throttle
        throttle(url); self.calls += 1; at = int(time.time() * 1000)
        request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (KolySvitlo official public document reader)', 'Referer': INDEX})
        with urllib.request.urlopen(request, timeout=35) as response:
            if urllib.parse.urlsplit(response.url).netloc != 'voe.com.ua': raise ValueError('source_authority_redirect')
            raw = response.read(8000001)
            if len(raw) > 8000000: raise ValueError('source_size_limit')
            item = {'url': url, 'status': response.status, 'checkedAt': at, 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
            if self.evidence:
                self.evidence.mkdir(parents=True, exist_ok=True); name = item['sha256'] + ('.pdf' if raw.startswith(b'%PDF') else '.html'); (self.evidence / name).write_bytes(raw); item['artifact'] = name
            self.trace.append(item); return raw, at

def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--operator', choices=['vinnytsia'], default='vinnytsia'); parser.add_argument('--target-city', default='Вінниця'); parser.add_argument('--output', required=True); parser.add_argument('--state'); parser.add_argument('--request-limit', type=request_limit, default=4); parser.add_argument('--full-city', action='store_true'); parser.add_argument('--evidence-directory'); args = parser.parse_args()
    geography = [g for g in json.loads(Path(__file__).with_name('capital-geography.json').read_text())['cities'] if g['regionId'] == 'UA-05' and city_key(g['settlement']) == city_key(args.target_city)]
    if len(geography) != 1: raise ValueError('unverified_target_geography')
    output = Path(args.output); output.parent.mkdir(parents=True, exist_ok=True); http = HTTP(args.request_limit, Path(args.evidence_directory) if args.evidence_directory else None)
    report = {'operatorId': 'vinnytsia', 'records': 0, 'errors': [], 'cityCrawl': {'targetCity': geography[0]['settlement'], 'mode': 'current-official-municipal-PDF-literal-houses', 'dictionaryComplete': False}}
    try:
        html, index_at = http.get(INDEX); document = current_document(html.decode('utf8'), index_at); raw, pdf_at = http.get(document['url'])
        if not raw.startswith(b'%PDF'): raise ValueError('source_is_not_pdf')
        claims, excerpts = city_claims(raw, document); checked_at = min(index_at, pdf_at); rows, observed, conflicts = consolidate(claims, geography[0], checked_at, document['effectiveUntil'])
        if not rows: raise ValueError('no_literal_city_house_facts')
        at = int(time.time() * 1000); packet = {'schemaVersion': 1, 'operatorId': 'vinnytsia', 'generatedAt': at, 'expiresAt': max(r['expiresAt'] for r in rows), 'records': rows, 'observedHouses': observed, 'completedStreetIds': []}
        output.write_text(json.dumps(packet, ensure_ascii=False, separators=(',', ':')) + '\n')
        report.update(document=document, records=len(rows), positiveHouses=sum(len(r['houses']) for r in rows), observedHouses=len(observed), conflicts=conflicts, excerpts=excerpts, checkedAt=checked_at); report['cityCrawl'].update(status='complete-document-partial-house-coverage', allMunicipalQueuesRead=True)
        if args.state:
            state = Path(args.state); state.parent.mkdir(parents=True, exist_ok=True); state.write_text(json.dumps({'schemaVersion': 1, 'lastCompleteAt': checked_at, 'documentSha256': http.trace[-1]['sha256']}) + '\n')
    except Exception as error: report['errors'].append({'error': type(error).__name__, 'reason': str(error)[:150]}); report['cityCrawl']['status'] = 'not-collected'
    finally:
        report['requests'] = http.trace; Path(str(output) + '.report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: report.get(k) for k in ('operatorId', 'records', 'positiveHouses', 'observedHouses', 'errors')}, ensure_ascii=False))
    if report['errors']: raise SystemExit(2)

if __name__ == '__main__': main()
