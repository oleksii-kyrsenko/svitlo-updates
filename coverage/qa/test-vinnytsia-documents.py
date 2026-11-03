import importlib.util, pathlib, sys, unittest
from types import SimpleNamespace
from unittest.mock import patch
ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('vinnytsia_documents', ROOT/'collect-vinnytsia-documents.py'); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
D = {'url': 'https://voe.com.ua/current.pdf', 'effectiveFrom': 1790812800000, 'effectiveUntil': 1806537600000}
G = {'regionId': 'UA-05', 'settlement': 'Вінниця', 'community': 'Вінницька міська громада'}
def word(text, x, y, width=20): return {'text': text, 'x0': x, 'x1': x+width, 'top': y, 'bottom': y+10}
def claim(text, queue='1.1'): return m.parse_paragraph({'text': text, 'queue': queue}, 1, D)

class OfficialDocuments(unittest.TestCase):
    def test_current_index_rejects_expired_comments_and_foreign_document(self):
        html = '<div class="component-file__title">ГПВ ВОЕ (з 1 жовтня 2026 року по 1 квітня 2027 року)</div><div class="component-file__btn"><a href="/current.pdf">Завантажити</a>'
        self.assertEqual(m.current_document(html,1793739000000)['url'],D['url'])
        for changed in ['<!--'+html+'-->', html.replace('2026 року','2025 року').replace('2027 року','2026 року'),html+html,html.replace('/current.pdf','https://other.example/current.pdf')]:
            with self.assertRaises(ValueError):m.current_document(changed,1793739000000)

    def test_actual_column_keeps_first_word_at43point8_and_excludes_queue_column(self):
        paragraphs=m.paragraphs([word('1.1',25,100,12),word('вул.Нова',43.8,100,45),word('8',95,100,5)])
        self.assertEqual(paragraphs[0]['text'],'вул.Нова 8')
        self.assertEqual(paragraphs[0]['queue'],'1.1')

    def test_competing_vertical_queue_labels_abstain(self):
        words=[word('1.1',25,100,12),word('вул.Нова',43.8,100,45),word('1.2',25,112,12),word('8',95,112,5)]
        self.assertFalse(m.paragraphs(words))

    def test_literal_house_suffixes_survive_but_initial_is_not_suffix(self):
        rows,obs,_=m.consolidate(claim('вул. Нова 8-А,9/2,13 М.Інша 54'),G,1793739000000,D['effectiveUntil'])
        self.assertEqual({h for r in rows for h in r['houses']},{'8-А','9/2','13'})
        self.assertNotIn('13 М',{o['house'] for o in obs})

    def test_numeric_ranges_are_not_expanded_and_veto_literal_other_queue(self):
        claims=claim('вул. Нова 1-9а,12-А')+claim('вул. Нова 3,15','2.1')
        rows,_,conflicts=m.consolidate(claims,G,1793739000000,D['effectiveUntil'])
        self.assertEqual({h for r in rows for h in r['houses']},{'12-А','15'})
        self.assertEqual(conflicts[0]['house'],'3')

    def test_numbered_lane_is_not_previous_street_house(self):
        rows,_,_=m.consolidate(claim('вул. Нова 3,3а,16,16а, 2 пров. Інший, 3'),G,1793739000000,D['effectiveUntil'])
        self.assertEqual({h for r in rows for h in r['houses']},{'3','3а','16','16а'})

    def test_untyped_name_never_guesses_street_but_can_veto(self):
        rows,_,_=m.consolidate(claim('вул. Нова 3,8')+claim('Нова, 3,15','2.1'),G,1793739000000,D['effectiveUntil'])
        self.assertEqual({h for r in rows for h in r['houses']},{'8'})

    def test_queue_conflict_and_partial_apartment_abstain_preserve_age(self):
        rows,obs,_=m.consolidate(claim('вул. Нова 3,9 кв.2; вул. Нова 12')+claim('вул. Нова 3','2.1'),G,1793739000000,D['effectiveUntil'])
        self.assertEqual({h for r in rows for h in r['houses']},{'12'})
        self.assertTrue(all(r['checkedAt']==1793739000000 and r['expiresAt']==1793825400000 for r in rows))
        self.assertTrue(all(o['checkedAt']==1793739000000 for o in obs))
        self.assertTrue(all('СО "ВМЕМ"' in r['quote'] for r in rows))

    def test_pdf_requires_complete_municipal_queue_scope(self):
        class PDF:
            pages=[SimpleNamespace(width=595.2,height=841.6,extract_text=lambda:'з 1 жовтня 2026 року по 1 квітня 2027 року\nСО "ВМЕМ"',extract_words=lambda:[word('1.1',25,100,12),word('вул.Нова',43.8,100,45),word('8',95,100,5)])]
            def __enter__(self):return self
            def __exit__(self,*args):pass
        with patch.object(m.pdfplumber,'open',return_value=PDF()):
            with self.assertRaisesRegex(ValueError,'incomplete_municipal_queue_section'):m.city_claims(b'PDF',D)

    def test_other_locality_rows_and_next_department_do_not_become_city_facts(self):
        paragraphs=[{'text':f'вул. Навчальна {a}{b}', 'queue':f'{a}.{b}', 'top':80, 'bottom':90} for a in range(1,7) for b in [1,2]]
        paragraphs.append({'text':'с.Агрономічне вул. Чужа 8', 'queue':'1.1', 'top':100, 'bottom':110})
        class PDF:
            pages=[SimpleNamespace(width=595.2,height=841.6,extract_text=lambda:'з 1 жовтня 2026 року по 1 квітня 2027 року\nСО "ВМЕМ"\nСО "ВЦЕМ"',extract_words=lambda:[word('"ВЦЕМ"',50,200),word('чужий_підрозділ',50,220)])]
            def __enter__(self):return self
            def __exit__(self,*args):pass
        with patch.object(m.pdfplumber,'open',return_value=PDF()),patch.object(m,'paragraphs',return_value=paragraphs) as collect:
            claims,excerpts=m.city_claims(b'PDF',D)
        self.assertEqual(len(excerpts),12)
        self.assertFalse(any(c['street']=='Чужа' for c in claims))
        self.assertEqual(collect.call_args.args[0],[])

if __name__=='__main__':unittest.main()
