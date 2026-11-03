import importlib.util, sys, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
spec = importlib.util.spec_from_file_location('cherkasy_documents', Path(__file__).resolve().parents[1] / 'collect-cherkasy-documents.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
G = {'regionId': 'UA-71', 'settlement': 'Черкаси', 'community': 'Черкаська міська громада'}
D = {'queue': '4.1', 'url': 'https://www.cherkasyoblenergo.com/public.pdf', 'effectiveFrom': 1790812800000, 'effectiveUntil': 1806537600000}

class OfficialDocuments(unittest.TestCase):
    def test_current_index_requires_every_queue_and_one_period(self):
        links = ''.join(f'<a href="/q{a}-{b}.pdf">{a} черга, {"І" * b} підчерга графіку погодинних відключень з 1 жовтня 2026 по 1 квітня 2027</a>' for a in range(1, 7) for b in range(1, 3))
        self.assertEqual(len(m.documents(links, 1793700000000)), 12)
        for changed in (links.replace('q6-2.pdf', 'q6-2.txt'), links.replace('/q6-2.pdf', 'https://other.example/q6-2.pdf'), links + links[:links.index('</a>') + 4]):
            with self.assertRaises(ValueError): m.documents(changed, 1793700000000)
        with self.assertRaises(ValueError): m.documents(links, 1806537600000)

    def test_pdf_department_cells_and_continuation_exclude_other_cities(self):
        head = 'Графік погодинного відключення з 01 жовтня 2026р. по 01 квітня 2027р. 4 черга. І підчерга'
        tables = [
            [['Назва підрозділу', 'Перелік'], ['Черкаські районні ЕМ', 'вул. Нова 1'], ['ВСП Черкаські міські ЕМ', 'вул. Нова 2']],
            [['Назва підрозділу', 'Перелік'], [None, 'вул. Нова 3'], ['Калинопільська філія', 'вул. Нова 4']]]
        class PDF:
            pages = [SimpleNamespace(extract_text=lambda: head, extract_tables=lambda t=t: [t]) for t in tables]
            def __enter__(self): return self
            def __exit__(self, *args): pass
        with patch.object(m.pdfplumber, 'open', return_value=PDF()): cells, departments = m.city_cells(b'public PDF', D)
        self.assertEqual([c['text'] for c in cells], ['вул. Нова 2', 'вул. Нова 3'])
        self.assertEqual(sum(d['target'] for d in departments), 1)

    def test_literal_current_public_document_excerpt_keeps_house_suffixes(self):
        # Actual official 4.1 PDF, page 25, SHA256
        # a5773967b7e01a8426874307518a559d3318d028c8fd79830ce04c5a03067604.
        claims = m.parse_cell({'page': 25, 'text': 'Кавказька, 75 , 75/1 , 76 , 76-А , 76-Б , 77 , 77/2 , 78 , Казбетська,3 , 3/2 , 4'}, D)
        self.assertEqual(claims[0]['street'], 'Кавказька')
        self.assertEqual(claims[0]['houses'], ['75', '75/1', '76', '76-А', '76-Б', '77', '77/2', '78'])
        self.assertEqual(claims[1]['street'], 'Казбетська')

    def test_unqualified_ranges_never_create_houses_and_veto_other_queue(self):
        a = m.parse_cell({'page': 1, 'text': 'вул. Навчальна 1-9, 12-А, 119/1-А'}, D)
        b = m.parse_cell({'page': 1, 'text': 'Навчальна, 3, 15'}, {**D, 'queue': '2.1'})
        rows, obs, conflicts = m.consolidate(a + b, G, 1000, D['effectiveUntil'])
        self.assertEqual({h for r in rows for h in r['houses']}, {'12-А', '119/1-А', '15'})
        self.assertEqual({o['house'] for o in obs}, {'12-А', '119/1-А', '3', '15'})
        self.assertEqual(conflicts[0]['house'], '3')

    def test_conflicting_documents_abstain_and_use_original_observation_age(self):
        a = m.parse_cell({'page': 1, 'text': 'вул. Навчальна 1, 2'}, D)
        b = m.parse_cell({'page': 2, 'text': 'Навчальна, 1'}, {**D, 'queue': '6.2'})
        rows, obs, conflicts = m.consolidate(a + b, G, 1000, 5000)
        self.assertEqual([r['houses'] for r in rows], [['2']])
        self.assertEqual(len(obs), 2); self.assertEqual(len(conflicts), 1)
        self.assertEqual((rows[0]['checkedAt'], rows[0]['expiresAt']), (1000, 5000))
        self.assertTrue(all(o['checkedAt'] == 1000 and o['expiresAt'] == 5000 for o in obs))

    def test_organization_and_numbered_feeder_are_not_streets(self):
        for text in ['ТОВ Приклад 18, 20', 'В РП-21 нормальний розрив', 'ОСББ Навчальне 17', 'Населення Калинопільської ОТГ 3']:
            self.assertFalse(m.parse_cell({'page': 1, 'text': text}, D))
        names = m.parse_cell({'page': 1, 'text': 'ТОВ "Приклад", вул.Навчальна, 1, 2; Вулиці: Нова, 3'}, D)
        self.assertEqual([(n['street'], n['houses']) for n in names], [('Навчальна', ['1', '2']), ('Нова', ['3'])])

    def test_street_name_and_apartment_qualifiers_do_not_promote_partial_house(self):
        self.assertEqual(m.street_name('І.Кулика'), 'І.Кулика')
        self.assertEqual(m.street_name('Пластунівська'), 'Пластунівська')
        claims = m.parse_cell({'page': 1, 'text': 'вул. Нова 3, 9 кв.2; вул. Нова 9, 12'}, D)
        rows, obs, conflicts = m.consolidate(claims, G, 1000, 5000)
        self.assertEqual({h for r in rows for h in r['houses']}, {'3', '12'})
        self.assertEqual({o['house'] for o in obs}, {'3', '9', '12'})

    def test_lane_boulevard_and_bare_names_cannot_be_conflated(self):
        claims = m.parse_cell({'page': 1, 'text': 'пров. Навчальний 1, 2; вул. Навчальний 3; б-р. Навчальний 4'}, D)
        claims += m.parse_cell({'page': 2, 'text': 'Навчальний, 1'}, {**D, 'queue': '2.1'})
        rows, obs, _ = m.consolidate(claims, G, 1000, 5000)
        self.assertEqual({(r['street'], h) for r in rows for h in r['houses']}, {('пров. Навчальний', '2'), ('вул. Навчальний', '3'), ('бульвар Навчальний', '4')})
        self.assertEqual(len(obs), 6)
        categories = m.parse_cell({'page': 3, 'text': 'Вулиці: Нова 1; Друга 2; Провулки: Ручай 3; Кривий 4'}, D)
        rows, _, _ = m.consolidate(categories, G, 1000, 5000)
        self.assertEqual({r['street'] for r in rows}, {'вул. Нова', 'вул. Друга', 'пров. Ручай', 'пров. Кривий'})

    def test_missing_street_type_is_not_invented(self):
        claims = m.parse_cell({'page': 1, 'text': 'Навчальна, 1, 2'}, D)
        rows, obs, _ = m.consolidate(claims, G, 1000, 5000)
        self.assertFalse(rows); self.assertFalse(obs)

if __name__ == '__main__': unittest.main()
