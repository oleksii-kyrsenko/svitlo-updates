import importlib.util
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from official_rosters import (explicit_houses, google_sheet_pages, rivne_city_records,
                              without_conflicts, zaporizhzhia_roster_links,
                              zaporizhzhia_sheet_records)


class OfficialRosterTests(unittest.TestCase):
    def test_house_letters_slashes_and_explicit_parity(self):
        self.assertEqual(explicit_houses('1А, 2-Б, 3/4, 5-9 (непарні), 10-14 (парні)', expand_ranges=True),
                         ['1А', '2-Б', '3/4', '5', '7', '9', '10', '12', '14'])
        self.assertEqual(explicit_houses('1-9, 3-7а, 2-8 (частково), 11'), ['11'])

    def test_rivne_explicit_houses_without_area_guess(self):
        table = [[['1', 'вул.Нова 2, 4А, 6-10 (парні), вул.Інша 5, 7; вул.Тиха частково; район Річковий 3', '1,2'],
                  ['2', 'вул.Лугова, вул.Квіткова 9, 11, Ліцей №3, ЗОШ №7', '2,1']]]
        rows = rivne_city_records(table, 'https://example.org/city.pdf', 1000, 'Рівненська міська громада')
        self.assertEqual([(r['street'], r['houses'], r['queue']) for r in rows],
                         [('вул.Нова', ['2', '4А', '6', '8', '10'], '1.2'),
                          ('вул.Інша', ['5', '7'], '1.2'), ('вул.Квіткова', ['9', '11'], '2.1')])
        self.assertTrue(all(r['scope'] == 'house' for r in rows))
        self.assertEqual(rivne_city_records(table, 'https://example.org/city.pdf', 1000, None), [])

    def test_rivne_conflicting_house_is_not_chosen(self):
        rows = rivne_city_records([[['1', 'вул.Нова 2, 4А', '1,2'], ['2', 'вул. Нова 4а, 6', '2,1']]],
                                  'https://example.org/city.pdf', 1000, 'Рівненська міська громада')
        self.assertEqual([r['houses'] for r in rows], [['2'], ['6']])

    def test_roster_links_require_official_city_queue_and_google_host(self):
        body = '<a href="https://docs.google.com/spreadsheets/d/demo/edit?gid=1">м. Запоріжжя, Черга 3, підчерга 2</a>'
        body += '<a href="https://docs.google.com/spreadsheets/d/other/edit">Черга 4, підчерга 1, інше місто</a>'
        body += '<a href="https://example.org/spreadsheets/d/bad/edit">м.Запоріжжя, Черга 3, підчерга 2</a>'
        self.assertEqual(zaporizhzhia_roster_links(body), [{'queue': '3.2', 'url': 'https://docs.google.com/spreadsheets/d/demo/htmlview'}])

    def test_sheet_page_decodes_data_without_executing_scripts(self):
        wrapper = r'pageUrl: "https:\/\/docs.google.com\/spreadsheets\/d\/demo\/htmlview\/sheet?headers\x3dtrue&gid=123"'
        self.assertEqual(google_sheet_pages(wrapper, 'https://docs.google.com/spreadsheets/d/demo/htmlview'),
                         ['https://docs.google.com/spreadsheets/d/demo/htmlview/sheet?headers=true&gid=123'])
        self.assertEqual(google_sheet_pages(wrapper, 'https://example.org/spreadsheets/d/demo/htmlview'), [])
        self.assertEqual(google_sheet_pages(wrapper, 'https://docs.google.com/spreadsheets/d/other/htmlview'), [])

    def test_sheet_header_corroborates_link_and_preserves_literal_buildings(self):
        body = '<table><tr><td colspan="2">3 черга 2 підчерга населення м.Запоріжжя</td></tr>'
        body += '<tr><td>Вулиця</td><td>Будинок</td></tr><tr><td>вул. Нова (Стара)</td><td>1|3А|5-11|13/2<br>15-Б</td></tr></table>'
        rows = zaporizhzhia_sheet_records(body, '3.2', 'https://docs.google.com/source', 1000, 'Запорізька міська громада')
        self.assertEqual(rows[0]['street'], 'вул. Нова')
        self.assertEqual(rows[0]['houses'], ['1', '3А', '13/2', '15-Б'])
        self.assertIn('Нова (Стара)', rows[0]['quote'])
        with self.assertRaises(ValueError):
            zaporizhzhia_sheet_records(body, '3.1', 'https://docs.google.com/source', 1000, 'Громада')
        with self.assertRaises(ValueError):
            zaporizhzhia_sheet_records(body.replace('Запоріжжя', 'Інше місто'), '3.2', 'https://docs.google.com/source', 1000, 'Громада')

    def test_unexpanded_other_queue_range_still_blocks_a_literal_claim(self):
        def sheet(queue, numbers):
            group, sub = queue.split('.')
            body = f'<table><tr><td>{group} черга {sub} підчерга населення м.Запоріжжя</td></tr><tr><td>вул. Нова</td><td>{numbers}</td></tr></table>'
            return zaporizhzhia_sheet_records(body, queue, 'https://docs.google.com/source', 1000, 'Громада')
        rows = without_conflicts(sheet('1.1', '1-9') + sheet('2.2', '3|7А|12'))
        self.assertEqual([r['houses'] for r in rows], [['12']])
        self.assertFalse(any('_uncertainRanges' in r for r in rows))


if __name__ == '__main__':
    unittest.main()
