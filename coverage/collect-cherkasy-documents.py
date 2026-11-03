"""Current official Cherkasy GPV PDFs: city department, literal street/house lists.

No application modules, test addresses, subscriber data or inferred queues.
All twelve queue documents must be read before any positive fact is emitted.
"""
import argparse, datetime, hashlib, io, json, re, time, urllib.parse, urllib.request
from html.parser import HTMLParser
from pathlib import Path
import pdfplumber
from city_crawl import city_key, request_limit, scoped_state
from source_utils import clean, record

INDEX = 'https://www.cherkasyoblenergo.com/perelik-gpv'
MONTHS = {v: i for i, v in enumerate('січня лютого березня квітня травня червня липня серпня вересня жовтня листопада грудня'.split(), 1)}
PREFIX = r'(?:(?:вулиця|бульвар|проспект|провулок|узвіз|площа)(?=\s)|(?:вул|ул|бульв|бул|б-р|просп|прс|пров|прв|пл)(?:\.|(?=\s)))'
LETTERS = 'А-Яа-яІіЇїЄєҐґA-Za-z'
HOUSE = rf'\d{{1,4}}(?:\s*-?\s*[{LETTERS}])?(?:/\d{{1,4}}(?:\s*-?\s*[{LETTERS}])?)?'
NAME = rf'[{LETTERS}][{LETTERS} .’\'\-]{{1,95}}?'
START = re.compile(rf'(?P<explicit>\b{PREFIX}\s*)(?P<name>{NAME})\s*,?\s*(?=\d)|(?:^|[;,])\s*(?P<bare>{NAME})\s*,?\s*(?=\d)', re.I)
TOKEN = re.compile(rf'(?:\d{{1,4}}\s*[-–—]\s*\d{{1,4}}|{HOUSE})(?![\w/–—-])')
TYPE_LABEL = {'street': 'вул. ', 'lane': 'пров. ', 'boulevard': 'бульвар ', 'avenue': 'просп. ', 'descent': 'узвіз ', 'square': 'пл. '}

def prefix_kind(value):
    value = value.casefold().strip(' .')
    if value.startswith(('пров', 'прв')): return 'lane'
    if value.startswith(('бул', 'б-р')): return 'boulevard'
    if value.startswith(('прос', 'прс')): return 'avenue'
    if value == 'узвіз': return 'descent'
    if value.startswith('пл'): return 'square'
    return 'street'

def milliseconds(value):
    return int(value.replace(tzinfo=datetime.timezone.utc).timestamp() * 1000)

def period(text):
    found = re.search(r'з\s+(\d{1,2})\s+(\w+)\s+(\d{4})(?:\s*р\.?)?\s+по\s+(\d{1,2})\s+(\w+)\s+(\d{4})', clean(text), re.I)
    if not found: raise ValueError('official_effective_period_missing')
    a, am, ay, b, bm, by = found.groups()
    return tuple(milliseconds(datetime.datetime(int(y), MONTHS[m.casefold()], int(d))) for d, m, y in [(a, am, ay), (b, bm, by)])

def queue(text):
    m = re.search(r'([1-6])\s+черга\s*[,.]\s*([ІI]{1,2})\s+підчерга', clean(text))
    return f'{m[1]}.{len(m[2])}' if m else None

class Links(HTMLParser):
    def __init__(self): super().__init__(convert_charrefs=True); self.current = None; self.links = []
    def handle_starttag(self, tag, attrs):
        if tag == 'a': self.current = [dict(attrs).get('href', ''), '']
    def handle_data(self, data):
        if self.current is not None: self.current[1] += data
    def handle_endtag(self, tag):
        if tag == 'a' and self.current is not None: self.links.append(self.current); self.current = None

def documents(html, at):
    parser = Links(); parser.feed(html); found = {}
    for href, label in parser.links:
        url = urllib.parse.urljoin(INDEX, href)
        if not urllib.parse.urlsplit(url).path.lower().endswith('.pdf') or not queue(label): continue
        if urllib.parse.urlsplit(url).netloc != urllib.parse.urlsplit(INDEX).netloc: raise ValueError('unexpected_document_authority')
        start, end = period(label)
        if not start <= at < end: continue
        q = queue(label)
        if q in found: raise ValueError('duplicate_current_queue_document')
        found[q] = {'url': url, 'label': clean(label), 'queue': q, 'effectiveFrom': start, 'effectiveUntil': end}
    if set(found) != {f'{a}.{b}' for a in range(1, 7) for b in range(1, 3)}: raise ValueError('incomplete_current_queue_document_set')
    if len({(d['effectiveFrom'], d['effectiveUntil']) for d in found.values()}) != 1: raise ValueError('inconsistent_effective_period')
    return [found[k] for k in sorted(found)]

def city_department(value):
    return bool(re.fullmatch(r'(?:ВСП\s+)?Черкаськ(?:і|а)\s+міськ(?:і|а)\s+(?:ЕМ|філія)', clean(value), re.I))

def city_cells(raw, document):
    """Actual PDF ruled cells establish department scope across page continuations."""
    cells = []; active = False; departments = []
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        heading = pdf.pages[0].extract_text() or ''
        if queue(heading) != document['queue'] or period(heading) != (document['effectiveFrom'], document['effectiveUntil']): raise ValueError('pdf_heading_disagrees_with_current_index')
        for number, page in enumerate(pdf.pages, 1):
            tables = page.extract_tables()
            if not tables: raise ValueError('official_table_geometry_missing')
            for table in tables:
                for row in table:
                    if len(row) != 2: raise ValueError('unexpected_official_table_columns')
                    left, right = [clean(v) for v in row]
                    if 'Графік погодинного' in left or 'Назва підрозділу' in left: continue
                    if left:
                        if queue(left): continue
                        active = city_department(left)
                        departments.append({'page': number, 'name': left, 'target': active})
                    if active and right: cells.append({'page': number, 'text': right})
    return cells, departments

def name_key(value):
    return re.sub(r'[\s.\-’\']+', '', value.casefold()).translate(str.maketrans('aceopx', 'асеорх'))

def house_key(value):
    return re.sub(r'[\s-]+', '', value.casefold()).translate(str.maketrans('aceopx', 'асеорх'))

def street_name(value):
    value = clean(value).strip(' .,:;')
    prefixes = list(re.finditer(rf'(?<![{LETTERS}])' + PREFIX, value, re.I))
    if prefixes: value = value[prefixes[-1].end():].strip(' .')
    # An organization name, feeder label or consumer category is not a street.
    if not value or value.endswith('-') or len(value) > 85 or re.fullmatch(r'вул|ул|пров|прв|просп|прс|пл|б-р|бул', value, re.I) or re.search(r'\b(?:ТОВ|ПП|ФОП|ФО|ПрАТ|АТ|КП|ОСББ|ВСП|КНП|ТГ|РП|КЕВ|школа|ступенів|підчерга|черга|населення|Вулиці|Вулиця|Провулки|кв|переїзд|уроч)\b', value, re.I): return None
    if not any(c.islower() for c in value) or len(value.split()) > 7: return None
    return value

def parse_cell(cell, document):
    text = cell['text']
    markers = [(m.start(), 'lane' if m[1].casefold().startswith('пров') else 'street') for m in re.finditer(r'(Вулиці|Провулки)\s*:', text, re.I)]
    # Preserve source offsets while making the category label a list boundary.
    text = re.sub(r'(Вулиці|Провулки)\s*:\s*;?\s*', lambda m: ';' + ' ' * (len(m[0]) - 1), text, flags=re.I)
    claims = []
    for match in START.finditer(text):
        raw_name = match['name'] or match['bare']; name = street_name(raw_name)
        if not name: continue
        explicit = match['explicit']
        embedded = list(re.finditer(rf'(?<![{LETTERS}])' + PREFIX, raw_name, re.I))
        if embedded: explicit = embedded[-1][0]
        preceding = [kind for offset, kind in markers if offset <= match.start()]
        kind = prefix_kind(explicit) if explicit else (preceding[-1] if preceding else None)
        position = match.end(); houses = []; unknown = []; ranges = []
        while position < len(text):
            separator = re.match(r'[\s,]*', text[position:]); position += separator.end()
            token = TOKEN.match(text, position)
            if not token: break
            literal = clean(token[0]); position = token.end()
            bounds = re.fullmatch(r'(\d+)\s*[-–—]\s*(\d+)', literal)
            if bounds:
                # The GPV document has no explicit parity/range legend. Retain
                # uncertainty to veto conflicting literal claims, never expand.
                lo, hi = map(int, bounds.groups())
                if lo <= hi: ranges.append([lo, hi])
            elif re.fullmatch(HOUSE, literal):
                if re.match(r'\s*[.,]?\s*(?:кв\.?|квартира|квартири|під[’\']?їзд)\b', text[position:], re.I): unknown.append(literal)
                else: houses.append(literal)
        if not houses and not ranges and not unknown: continue
        claim = {'street': name, 'kind': kind, 'houses': list(dict.fromkeys(houses)), 'ranges': ranges, 'queue': document['queue'], 'sourceUrl': document['url'], 'page': cell['page'], 'excerpt': text[match.start():position].strip(' ;,')[:2400]}
        if houses or ranges: claims.append(claim)
        if unknown: claims.append({**claim, 'houses': unknown, 'ranges': [], 'queue': None})
    return claims

def consolidate(claims, geography, checked_at, effective_until):
    known_types = {}
    for claim in claims:
        if claim.get('kind'): known_types.setdefault(name_key(claim['street']), set()).add(claim['kind'])
    typed = []
    for claim in claims:
        kinds = {claim['kind']} if claim.get('kind') else known_types.get(name_key(claim['street']), set())
        # An unqualified name never becomes a guessed lane/street. If several
        # explicit types exist, retain negative observations for each candidate.
        for kind in kinds:
            typed.append({**claim, 'street': TYPE_LABEL[kind] + claim['street'], 'queue': claim['queue'] if len(kinds) == 1 else None})
    grouped = {}; ranges = {}
    for claim in typed:
        key = name_key(claim['street'])
        for bounds in claim['ranges']: ranges.setdefault(key, []).append((*bounds, claim['queue']))
        for literal in claim['houses']: grouped.setdefault((key, house_key(literal)), []).append((literal, claim))
    rows = []; observations = []; conflicts = []
    expiry = min(checked_at + 86400000, effective_until)
    for (street_key, _), values in grouped.items():
        literal, claim = values[0]; qs = {c['queue'] for _, c in values}; number = int(re.match(r'\d+', literal)[0])
        q = next(iter(qs)) if len(qs) == 1 else None
        if any(lo <= number <= hi and rq != q for lo, hi, rq in ranges.get(street_key, [])): q = None
        observation = {k: geography[k] for k in ('regionId', 'settlement', 'community')}
        observation.update(street=claim['street'], house=literal, checkedAt=checked_at, expiresAt=expiry)
        observations.append(observation)
        if q is None:
            conflicts.append({'street': claim['street'], 'house': literal, 'queues': sorted(str(v) for v in qs)})
            continue
        row = record('cherkasy', geography['regionId'], geography['settlement'], geography['community'], claim['street'], literal, q, claim['sourceUrl'], checked_at)
        row.update(expiresAt=expiry, quote=f"Черкаські міські ЕМ; PDF стор. {claim['page']}; черга {q}. {claim['excerpt']}", quoteType='official-document-excerpt')
        rows.append(row)
    # The same quoted public list should not be duplicated once per house.
    # Group only verified literal houses; keep per-house negative observations.
    groups = {}
    for row in rows:
        key = (name_key(row['street']), row['queue'], row['sourceUrl'])
        groups.setdefault(key, []).append(row)
    compact = []
    for key, values in groups.items():
        for index in range(0, len(values), 1000):
            chunk = values[index:index + 1000]; row = dict(chunk[0]); row['houses'] = [r['houses'][0] for r in chunk]
            row['id'] = hashlib.sha256(('cherkasy|'+ '|'.join(key) + '|' + str(index // 1000)).encode()).hexdigest()[:24]
            pages = sorted({int(re.search(r'PDF стор\. (\d+)', r['quote'])[1]) for r in chunk})
            excerpt = row['quote'].split('. ', 2)[-1]
            row['quote'] = f"Черкаські міські ЕМ; PDF стор. {', '.join(map(str, pages))}; черга {row['queue']}. Приклад дослівного адресного рядка: {excerpt}"[:2500]
            compact.append(row)
    return compact, observations, conflicts

class HTTP:
    def __init__(self, limit, directory): self.limit = limit; self.calls = 0; self.trace = []; self.directory = directory; self.deadline = time.monotonic() + 480
    def get(self, url):
        if self.calls >= self.limit or time.monotonic() > self.deadline: raise ValueError('request_budget')
        from request_budget import throttle
        throttle(url); self.calls += 1
        item = {'url': url, 'checkedAt': int(time.time() * 1000)}
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (KolySvitlo official public document reader)'}), timeout=35) as response:
                raw = response.read(16000001)
                if len(raw) > 16000000: raise ValueError('source_size_limit')
                if urllib.parse.urlsplit(response.url).netloc != urllib.parse.urlsplit(INDEX).netloc: raise ValueError('source_authority_redirect')
                item.update(status=response.status, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
                if self.directory:
                    self.directory.mkdir(parents=True, exist_ok=True); suffix = '.pdf' if raw.startswith(b'%PDF') else '.html'; target = self.directory / (item['sha256'] + suffix); target.write_bytes(raw); item['artifact'] = target.name
                return raw, item['checkedAt']
        except Exception as error: item.update(status=getattr(error, 'code', None), error=type(error).__name__); raise
        finally: self.trace.append(item)

def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--operator', choices=['cherkasy'], default='cherkasy'); p.add_argument('--target-city', default='Черкаси'); p.add_argument('--output', required=True); p.add_argument('--state'); p.add_argument('--request-limit', type=request_limit, default=20); p.add_argument('--full-city', action='store_true'); p.add_argument('--evidence-directory'); args = p.parse_args()
    geography = [g for g in json.loads(Path(__file__).with_name('capital-geography.json').read_text())['cities'] if g['regionId'] == 'UA-71' and city_key(g['settlement']) == city_key(args.target_city)]
    if len(geography) != 1: raise ValueError('verified_target_geography_required')
    g = geography[0]; output = Path(args.output); statefile = Path(args.state) if args.state else output.with_suffix('.state.json'); saved = json.loads(statefile.read_text()) if statefile.exists() else {}; state = scoped_state(saved, args.target_city, True)
    http = HTTP(args.request_limit, Path(args.evidence_directory) if args.evidence_directory else None); rows = []; observations = []; errors = []; sources = []; claims = []; conflicts = []; complete = False
    try:
        html, index_at = http.get(INDEX); docs = documents(html.decode('utf-8'), index_at); ats = [index_at]
        for doc in docs:
            raw, at = http.get(doc['url']); ats.append(at)
            if not raw.startswith(b'%PDF'): raise ValueError('official_document_is_not_pdf')
            cells, departments = city_cells(raw, doc); extracted = [c for cell in cells for c in parse_cell(cell, doc)]; claims.extend(extracted)
            sources.append({**doc, 'checkedAt': at, 'sha256': hashlib.sha256(raw).hexdigest(), 'cityCells': len(cells), 'claims': len(extracted), 'departments': departments, 'excerpts': cells})
        checked_at = min(ats); rows, observations, conflicts = consolidate(claims, g, checked_at, min(d['effectiveUntil'] for d in docs)); complete = True
        state.update(lastCompleteAt=checked_at, documentHashes=[s['sha256'] for s in sources])
    except Exception as error: errors.append({'stage': 'official_documents', 'error': type(error).__name__, 'reason': str(error)[:200], 'httpStatus': getattr(error, 'code', None)})
    at = int(time.time() * 1000); output.parent.mkdir(parents=True, exist_ok=True); statefile.parent.mkdir(parents=True, exist_ok=True); statefile.write_text(json.dumps(saved, ensure_ascii=False, indent=2) + '\n')
    report = {'operatorId': 'cherkasy', 'checkedAt': at, 'records': len(rows), 'observedHouses': len(observations), 'conflicts': conflicts, 'requestCount': http.calls, 'requests': http.trace, 'errors': errors, 'sources': sources, 'cityCrawl': {'targetCity': g['settlement'], 'mode': 'official-current-GPV-city-house-documents', 'status': 'complete' if complete else 'partial', 'dictionaryComplete': False, 'allCurrentQueueDocumentsRead': complete, 'queueDocuments': len(sources)}, 'method': 'Source-derived literal official house facts; document traversal is not independent Android UI coverage or a complete city address inventory. Unqualified ranges are never expanded.'}
    Path(str(output) + '.report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    if complete and observations:
        bundle = {'schemaVersion': 1, 'operatorId': 'cherkasy', 'generatedAt': at, 'expiresAt': max(o['expiresAt'] for o in observations), 'records': rows, 'observedHouses': observations, 'completedStreetIds': []}; output.write_text(json.dumps(bundle, ensure_ascii=False, separators=(',', ':')) + '\n')
    print(json.dumps({k: report[k] for k in ('operatorId', 'records', 'observedHouses', 'requestCount', 'errors')}, ensure_ascii=False))
    if not complete or not observations: raise SystemExit(2)

if __name__ == '__main__': main()
