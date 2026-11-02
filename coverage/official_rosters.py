"""Conservative official roster decoders, independent of application code.

Bare street names, implied parity, landmarks and partial-area descriptions never
become house assignments. The original row remains the evidence for every item.
"""
import hashlib
import html
import json
import re
import urllib.parse
from html.parser import HTMLParser


def clean(value):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]*>', ' ', str(value or '')))).strip()


def literal_house(value):
    value = re.sub(r'\s+', '', clean(value)).strip(' .;')
    return value if re.fullmatch(r'\d{1,4}(?:-?[А-Яа-яІіЇїЄєҐґA-Za-z])?(?:/\d{1,4}[А-Яа-яІіЇїЄєҐґA-Za-z]?)?', value) else None


def explicit_houses(value, *, separator=r'[,;]', expand_ranges=False):
    """Expand only numerically bounded ranges with an explicit parity marker.

    A notation such as 1-7 can mean odd-side houses or the entire interval. Its
    endpoints alone do not prove the intended set, so retain no guessed houses.
    """
    out = []
    for part in re.split(separator, value):
        part = clean(part).strip(' .;')
        if not part:
            continue
        house = literal_house(part)
        if house:
            out.append(house)
            continue
        match = re.fullmatch(r'(\d{1,4})\s*[-–—]\s*(\d{1,4})\s*\((непарні|парні|усі|всі)\)', part, re.I)
        if expand_ranges and match:
            start, end = int(match[1]), int(match[2])
            if not 0 < start <= end <= start + 500:
                continue
            parity = 1 if match[3].casefold() == 'непарні' else 0 if match[3].casefold() == 'парні' else None
            out.extend(str(n) for n in range(start, end + 1) if parity is None or n % 2 == parity)
    return list(dict.fromkeys(out))


def house_key(value):
    return re.sub(r'[\s-]', '', value).casefold()


def street_key(value):
    value = clean(value).casefold()
    value = re.sub(r'^(?:вул\.?|вулиця)\s*', 'вул. ', value)
    return re.sub(r'\s+', ' ', value).strip(' ,.')


def without_conflicts(rows):
    claims = {}
    ranges = {}
    for row in rows:
        key = (row['settlement'], street_key(row['street']))
        for house in row.get('houses', []):
            claims.setdefault((*key, house_key(house)), set()).add(row['queue'])
        for start, end in row.get('_uncertainRanges', []):
            ranges.setdefault(key, []).append((start, end, row['queue']))
    for row in rows:
        key = (row['settlement'], street_key(row['street']))
        safe = []
        for house in row.get('houses', []):
            queues = set(claims[(*key, house_key(house))])
            number = re.match(r'\d+', house)
            if number:
                queues.update(queue for start, end, queue in ranges.get(key, []) if start <= int(number[0]) <= end)
            if queues == {row['queue']}:
                safe.append(house)
        row['houses'] = safe
        row.pop('_uncertainRanges', None)
    return [row for row in rows if row['houses']]


def uncertain_ranges(numbers):
    """Range mentions block conflicting literal claims even when not expanded."""
    return [[int(m[1]), int(m[2])] for m in re.finditer(r'(?<!\d)(\d{1,4})\s*[-–—]\s*(\d{1,4})', numbers)
            if 0 < int(m[1]) <= int(m[2]) <= 9999]


def add_range_claim(rows, row, operator, city, street, queue, numbers):
    possible = uncertain_ranges(numbers)
    if row:
        if possible:
            row['_uncertainRanges'] = possible
        rows.append(row)
    elif possible:
        rows.append({'operatorId': operator, 'settlement': city, 'street': street,
                     'queue': queue, 'houses': [], '_uncertainRanges': possible})


def record(operator, region, city, community, street, houses, queue, url, quote, now):
    if not community or not houses or not re.fullmatch(r'[1-6]\.[12]', queue):
        return None
    digest = hashlib.sha256('|'.join([operator, city, community, street, queue, quote]).encode()).hexdigest()[:24]
    return {'id': digest, 'regionId': region, 'settlement': city, 'community': community,
            'street': street, 'scope': 'house', 'houses': houses, 'queue': queue,
            'sourceUrl': url, 'quote': quote[:2500], 'quoteType': 'structured-official-fields',
            'checkedAt': now, 'expiresAt': now + 86400000, 'official': True}


# The PDF has a street-name / house-number column; unprefixed street names in
# that column inherit its usual 'вул.' type, never from a neighbouring locality.
_TYPE = r'(?:вул[.,]?|вулиця|пров\.?|провулок|проспект|просп\.?|пр\.|пл\.?|площа|м-н|бульвар|бул\.?)'
_LANDMARK = re.compile(r'№|\b(?:район|р-н|ліцей|школ|зош|тц|тов|кп|ппф|жк|ринок|завод|гараж|станція|садок|поліклініка|театр|магазин|село|с\.)\b', re.I)


def rivne_city_records(tables, url, now, community):
    rows = []
    for table in tables:
        for cells in table:
            if len(cells) != 3:
                continue
            _, raw, queue = [clean(value) for value in cells]
            queue = queue.replace(',', '.')
            if not re.fullmatch(r'[1-6]\.[12]', queue) or not raw:
                continue
            # Explicit markers begin a new street even when the PDF omits a
            # comma. Periods after initial letters are not address boundaries.
            text = re.sub(r'(?<!^)(?<![А-Яа-яІіЇїЄєҐґ])(?=' + _TYPE + r'\s*)', ';', raw, flags=re.I)
            for chunk in text.split(';'):
                chunk = chunk.strip(' ,.;')
                # Separate an unprefixed next street after a house list. Only
                # literal house lists with a clear new name are considered.
                pieces = re.split(r',\s*(?=[А-Яа-яІіЇїЄєҐґA-Za-z][^,;]*?\s+\d)', chunk)
                for piece in pieces:
                    if re.search(r'частков|приватн|промзон|біля|перехрест|\+|селищ', piece, re.I):
                        continue
                    # The first house must follow a name; a numeric street
                    # name (16 Липня) remains part of that name.
                    match = re.fullmatch(r'(.+?[А-Яа-яІіЇїЄєҐґA-Za-z\'])\s*[, ]\s*(\d.*)', piece)
                    if not match:
                        continue
                    street, numbers = match[1].strip(' ,.'), match[2]
                    if _LANDMARK.search(street):
                        continue
                    # A following school/business is a new entity; numbers
                    # after that entity cannot be carried back to this street.
                    numbers = re.split(r',\s*(?=[^\d\s])', numbers, maxsplit=1)[0]
                    if not re.match(r'^' + _TYPE + r'\s*', street, re.I):
                        street = 'вул. ' + street
                    houses = explicit_houses(numbers, expand_ranges=True)
                    row = record('rivne', 'UA-56', 'Рівне', community, street, houses, queue, url,
                                 f'м.Рівне; підчерга {queue}; рядок офіційної таблиці: {raw}', now)
                    add_range_claim(rows, row, 'rivne', 'Рівне', street, queue, numbers)
    return without_conflicts(rows)


class Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.href = None
        self.text = ''
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.href = dict(attrs).get('href')
            self.text = ''

    def handle_data(self, data):
        if self.href is not None:
            self.text += data

    def handle_endtag(self, tag):
        if tag == 'a' and self.href is not None:
            self.links.append((self.href, clean(self.text)))
            self.href = None


def zaporizhzhia_roster_links(body):
    parser = Links()
    parser.feed(body)
    out = []
    for url, label in parser.links:
        parsed = urllib.parse.urlsplit(url)
        queue = re.fullmatch(r'м\.\s*Запоріжжя\s*,?\s*Черга\s*([1-6])\s*,?\s*підчерга\s*([12])', label, re.I)
        sheet = re.match(r'^/spreadsheets/d/([-\w]+)/', parsed.path)
        if parsed.scheme == 'https' and parsed.hostname == 'docs.google.com' and queue and sheet:
            out.append({'queue': queue[1] + '.' + queue[2], 'url': f'https://docs.google.com/spreadsheets/d/{sheet[1]}/htmlview'})
    return list({(item['queue'], item['url']): item for item in out}.values())


def google_sheet_pages(body, wrapper_url):
    parsed = urllib.parse.urlsplit(wrapper_url)
    if parsed.scheme != 'https' or parsed.hostname != 'docs.google.com':
        return []
    prefix = re.match(r'^(/spreadsheets/d/[-\w]+/)', parsed.path)
    if not prefix:
        return []
    out = []
    # Decode a quoted JS string as data; do not execute scripts from a source.
    for match in re.finditer(r'pageUrl:\s*"((?:\\.|[^"\\])*)"', body):
        try:
            token = re.sub(r'\\x([0-9a-fA-F]{2})', r'\\u00\1', match[1])
            url = json.loads('"' + token + '"')
            target = urllib.parse.urlsplit(url)
            if target.scheme == 'https' and target.hostname == 'docs.google.com' and target.path == prefix[1] + 'htmlview/sheet':
                out.append(url)
        except (ValueError, TypeError):
            pass
    return list(dict.fromkeys(out))


class SheetRows(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.cells = []
        self.cell = None
        self.rows = []

    def handle_starttag(self, tag, attrs):
        if tag == 'tr':
            self.cells = []
        if tag == 'td':
            self.cell = ''
        if tag == 'br' and self.cell is not None:
            self.cell += '|'

    def handle_data(self, data):
        if self.cell is not None:
            self.cell += data

    def handle_endtag(self, tag):
        if tag == 'td' and self.cell is not None:
            self.cells.append(clean(self.cell))
            self.cell = None
        if tag == 'tr' and self.cells:
            self.rows.append(self.cells)


def zaporizhzhia_sheet_records(body, queue, url, now, community):
    parser = SheetRows()
    parser.feed(body)
    group, sub = queue.split('.')
    # Check the document's own city/queue heading against the official link.
    header = ' '.join(' '.join(row) for row in parser.rows[:3])
    if not re.search(rf'{group}\s*черга\s*{sub}\s*підчерга\b.*?населення\s*м\.\s*Запоріжжя', header, re.I):
        raise ValueError('roster_city_or_queue_header_mismatch')
    out = []
    for cells in parser.rows:
        if len(cells) != 2 or not re.match(r'^' + _TYPE + r'\s*', cells[0], re.I):
            continue
        street, numbers = cells
        # Parentheses in the street column provide the former official name;
        # retain it in the quote, use the current label for address matching.
        current = re.sub(r'\s*\([^()]+\)\s*$', '', street).strip()
        houses = explicit_houses(numbers, separator=r'\|', expand_ranges=True)
        for start in range(0, max(1, len(houses)), 1000):
            row = record('zaporizhzhia', 'UA-23', 'Запоріжжя', community, current,
                         houses[start:start + 1000], queue, url,
                         f'м.Запоріжжя; черга {queue}; {street}; будинки: {numbers}', now)
            add_range_claim(out, row, 'zaporizhzhia', 'Запоріжжя', current, queue, numbers)
    return out
