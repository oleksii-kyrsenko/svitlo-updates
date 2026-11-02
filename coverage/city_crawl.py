"""Shared bounded city crawl controls. City names are supplied by sourced metadata.

A targeted crawl may span many runs. Reaching a request bound is partial progress,
never evidence that a city dictionary is complete.
"""
import hashlib
import re
import unicodedata

class RequestLimit(RuntimeError):
    pass


def city_key(value):
    value = unicodedata.normalize('NFKC', str(value or '')).casefold().strip()
    value = re.sub(r'\s*\([^()]*громада\)\s*$', '', value)
    value = re.sub(r'^(?:(?:м|с)\.\s*|місто\s+|село\s+|смт\.?\s+|селище\s+)', '', value)
    return re.sub(r'\s+', ' ', value).strip()


def select_city(cities, target, label='name'):
    if not target:
        return cities
    found = [city for city in cities if city_key(city.get(label)) == city_key(target)]
    if len(found) != 1:
        raise ValueError('target_city_not_unique' if found else 'target_city_not_found')
    return found


def scoped_state(state, target, full_city=False):
    """Keep the old cursor untouched and isolate city-specific crawl positions."""
    if not target and not full_city:
        return state
    key = hashlib.sha256((city_key(target) or '*').encode()).hexdigest()[:20]
    return state.setdefault('cityCrawls', {}).setdefault(key, {})


def request_limit(value):
    value=int(value)
    if not 1 <= value <= 2000:
        raise ValueError('unbounded_request_limit')
    return value


def crawl_report(state, target, full_city):
    return {'targetCity': target or None, 'mode': 'city-directory' if full_city else 'bounded-sample',
            'status': state.get('crawlStatus', 'partial'),
            'dictionaryComplete': state.get('dictionaryComplete', False)}

# Public labels may contain Ukrainian/Russian/Latin names, digits and punctuation.
# Unsupported source alphabet or search semantics cannot establish completeness.
SEARCH_ALPHABET = " абвгґдеєжзиіїйклмнопрстуфхцчшщьюяыэъёabcdefghijklmnopqrstuvwxyz0123456789.-’'()/№"


def search_inventory(fetch, state, *, cap, initial_queries, max_queries=20, label='value'):
    """Resume ordinary autocomplete queries; retain source IDs before next query.

    A capped response is expanded, rather than silently assuming its first page
    is the whole dictionary. Search completion is separate from verified source
    directory completeness: APIs may enforce minimum search length or use other
    undisclosed filters.
    """
    state.setdefault('queries', list(initial_queries))
    state.setdefault('done', [])
    state.setdefault('items', {})
    state.setdefault('unexpanded', [])
    for _ in range(max_queries):
        if not state['queries']:
            break
        term = state['queries'][0]
        response = fetch(term)
        if not isinstance(response, list) or any(not isinstance(row, dict) or row.get('id') is None or not isinstance(row.get(label), str) for row in response):
            raise ValueError('invalid_autocomplete_dictionary')
        for row in response:
            state['items'][str(row['id'])] = {'id': row['id'], label: row[label]}
        state['queries'].pop(0)
        state['done'].append(term)
        if len(response) >= cap:
            if len(term) < 80 and len(state['queries']) + len(state['done']) < 20000:
                known = set(state['queries']) | set(state['done'])
                for char in SEARCH_ALPHABET:
                    if term + char not in known:
                        state['queries'].append(term + char)
            else:
                state['unexpanded'].append(term)
    return list(state['items'].values())
