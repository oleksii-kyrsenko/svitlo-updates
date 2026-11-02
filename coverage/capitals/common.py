"""Small, dependency-free helpers for the independent capital-address audit."""
import hashlib
import json
import math
import pathlib
import re
from datetime import datetime, timezone


def digest(value):
    return hashlib.sha256(value).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def read_json(path):
    return json.loads(pathlib.Path(path).read_text())


def write_json(path, value):
    pathlib.Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError('timestamp must be a timezone-aware ISO8601 string')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('timestamp must include a timezone')
    return result.astimezone(timezone.utc)


def address_identity(case):
    """Frozen geographic identity, independent of a queue or displayed alias."""
    keys = ('regionId', 'city', 'osmType', 'osmId', 'latitude', 'longitude', 'exactStreet', 'exactHouse')
    if any(case.get(k) is None or case.get(k) == '' for k in keys):
        raise ValueError('incomplete frozen address: ' + str(case.get('id')))
    return digest(canonical({k: case[k] for k in keys}))


def normal(value):
    return re.sub(r'\s+', ' ', str(value).lower().replace('’', "'").replace('ʼ', "'")).strip(' .,')


def street_identity(value):
    value = normal(value)
    for kind, aliases in (
        ('вулиця', r'вулиця|вул\.?'), ('провулок', r'провулок|пров\.?'),
        ('проспект', r'проспект|просп\.?|пр-т'), ('площа', r'площа|пл\.?'),
        ('бульвар', r'бульвар|бульв\.?|бул\.?'), ('узвіз', r'узвіз'),
        ('набережна', r'набережна'), ('шосе', r'шосе'), ('алея', r'алея'),
        ('тупик', r'тупик'), ('проїзд', r'проїзд'), ('дорога', r'дорога')):
        prefix = re.match(r'^(?:' + aliases + r')\s+', value)
        suffix = re.search(r'\s+(?:' + aliases + r')$', value)
        if prefix:
            return kind, normal(value[prefix.end():])
        if suffix:
            return kind, normal(value[:suffix.start()])
    return '', value


def distance_km(a, b):
    lat1, lon1 = map(math.radians, (float(a['latitude']), float(a['longitude'])))
    lat2, lon2 = map(math.radians, (float(b['latitude']), float(b['longitude'])))
    return 6371.0088 * 2 * math.asin(min(1, math.sqrt(
        math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)))


def checked_artifact(root, reference):
    """Every accepted claim must retain the exact referenced local evidence."""
    if not isinstance(reference, dict) or not re.fullmatch(r'[a-f0-9]{64}', str(reference.get('sha256', ''))):
        raise ValueError('artifact requires a SHA256 reference')
    root = pathlib.Path(root).resolve()
    name = pathlib.PurePosixPath(str(reference.get('path', '')))
    if not name.parts or name.is_absolute() or '..' in name.parts:
        raise ValueError('artifact path must be relative and contained in the evidence directory')
    path = (root / str(name)).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError('missing/escaping artifact: ' + str(name))
    data = path.read_bytes()
    if digest(data) != reference['sha256']:
        raise ValueError('artifact hash mismatch: ' + str(name))
    return data
