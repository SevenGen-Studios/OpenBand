from copy import deepcopy
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from tools.bandy_corpus import atomic_json, finalize, inventory, read_checkpoint, resolve_observations
from tools.bandy_financial import column_layout, extract_fixture, identity_issues, is_statement
from tools.bandy_ocr_recovery import merge_recoveries, ocr_words


class BandyCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = json.loads(Path('tests/fixtures/bandy-sk/391-2024-2025.json').read_text(encoding='utf-8'))
        cls.records = extract_fixture(fixture)['records']

    def test_inventory_includes_missing_nations_and_posted_sources_only(self):
        filing = {'year': '2024-2025', 'docType': 'Audited consolidated financial statements',
                  'href': 'https://example.test/a.pdf', 'posted': True}
        data = {'bands': [{'id': 1, 'name': 'One', 'province': 'SK', 'filings': [filing, filing,
                          dict(filing, year='2025-2026', href=None, posted=False)]},
                         {'id': 2, 'name': 'Two', 'province': 'AB', 'filings': []}]}
        result = inventory(data, {})
        self.assertEqual(len(result['nations']), 2)
        self.assertEqual(len(result['documents']), 1)
        self.assertEqual(result['nations'][0]['missingFilingYears'], ['2025-2026'])
        self.assertEqual(result['nations'][1]['documentKeys'], [])

    def test_known_source_hash_is_preserved(self):
        data = {'bands': [{'id': 1, 'name': 'One', 'province': 'SK', 'filings': [
            {'year': '2024-2025', 'docType': 'Audited financial statements',
             'href': 'https://example.test/a.pdf', 'posted': True, 'sha256': 'a'*64}]}]}
        self.assertEqual(inventory(data, {})['documents'][0]['expectedSha256'], 'a'*64)

    def test_equal_sources_coalesce_and_retain_provenance_links(self):
        original = next(r for r in self.records if r['metric']=='cash' and not r['comparative'])
        other = deepcopy(original)
        other.update(recordId='b'*64, sourceDocumentSha256='c'*64, comparative=True, sourceFiscalYear='2025-2026')
        observations, canonical, links, conflicts = resolve_observations([original, other])
        self.assertEqual(len(observations), 2)
        self.assertEqual(len(canonical), 1)
        self.assertEqual(len(links), 2)
        self.assertEqual(conflicts, [])
        self.assertFalse(canonical[0]['comparative'])
        self.assertEqual(canonical[0]['validationStatus'], 'machine_checked')

    def test_conflicting_comparative_does_not_overwrite_or_pass_checks(self):
        original = next(r for r in self.records if r['metric']=='cash' and not r['comparative'])
        other = deepcopy(original)
        other.update(recordId='b'*64, sourceDocumentSha256='c'*64, comparative=True, sourceFiscalYear='2025-2026')
        other['value'] += 100
        observations, canonical, links, conflicts = resolve_observations([original, other])
        self.assertEqual(len(conflicts), 1)
        self.assertTrue(all(r['validationStatus']=='manual_review' for r in observations))
        self.assertEqual(canonical[0]['value'], original['value'])
        self.assertEqual(canonical[0]['validationStatus'], 'manual_review')
        self.assertEqual({r['value'] for r in observations}, {original['value'], other['value']})

    def test_checked_corroborating_source_preferred_to_unchecked_equal_source(self):
        original = next(r for r in self.records if r['metric']=='cash' and not r['comparative'])
        other = deepcopy(original)
        original = deepcopy(original)
        original.update(validationStatus='manual_review', validationFlags=['source_hash_changed'])
        other.update(recordId='b'*64, sourceDocumentSha256='c'*64, comparative=True, sourceFiscalYear='2025-2026')
        _, canonical, _, _ = resolve_observations([original, other])
        self.assertEqual(canonical[0]['recordId'], other['recordId'])
        self.assertEqual(canonical[0]['validationStatus'], 'machine_checked')

    def test_date_caption_can_share_the_explicit_year_header(self):
        fixture = json.loads(Path('tests/fixtures/bandy-sk/391-2024-2025.json').read_text(encoding='utf-8'))
        page = next(p for p in fixture['pages'] if p['page']==6)
        page['words'].append({'text': 'March', 'x0': 50, 'x1': 85, 'top': 102.35, 'bottom': 111.35})
        columns, issue = column_layout(page, '2024-2025')
        self.assertIsNone(issue)
        self.assertEqual([c['year'] for c in columns if c['role']=='actual'], [2025,2024])

    def test_explicit_unnumbered_budget_column_is_excluded(self):
        fixture = json.loads(Path('tests/fixtures/bandy-sk/391-2024-2025.json').read_text(encoding='utf-8'))
        page = next(p for p in fixture['pages'] if p['page']==6)
        page['words'] = [w for w in page['words'] if not (w['text']=='2025' and w['x1']<450)]
        columns, issue = column_layout(page, '2024-2025')
        self.assertIsNone(issue)
        self.assertEqual(len(columns), 3)
        self.assertEqual(sum(c['role']=='budget' for c in columns), 1)

    def test_table_of_contents_is_not_a_statement(self):
        page = {'text': 'Enoch Cree Nation\nConsolidated Financial Statements\nMarch 31, 2025 Page\nManagement Responsibility 3\nFinancial Statements\nConsolidated Statement of Financial Position 6\nConsolidated Statement of Operations and Accumulated Surplus 8'}
        self.assertFalse(is_statement(page))

    def test_title_split_around_a_date_caption(self):
        page = {'text': 'ONE ARROW FIRST NATION\nCONSOLIDATED STATEMENT OF FOR THE YEAR ENDED\nOPERATIONS AND ACCUMULATED SURPLUS MARCH 31\nBudget 2024 2023\nREVENUE'}
        self.assertTrue(is_statement(page))
        page['text'] = page['text'].replace('OPERATIONS AND ACCUMULATED SURPLUS', 'CASH FLOWS')
        self.assertFalse(is_statement(page))

    def test_plural_auditor_and_letter_spacing_confirm_identity(self):
        document = {'bandId':'391','bandName':'George Gordon First Nation','fiscalYear':'2024-2025',
                    'sourceUrl':'https://example.test/source.pdf','sha256':'a'*64}
        pages = [{'text':'G eorge Gordon First N ation\nIndependent Auditors\' Report'}]
        self.assertEqual(identity_issues(document,pages), [])

    def test_surplus_currency_symbol_is_not_us_dollars(self):
        document = {'bandId':'391','bandName':'George Gordon First Nation','fiscalYear':'2024-2025',
                    'sourceUrl':'https://example.test/source.pdf','sha256':'a'*64}
        page = {'text':'George Gordon First Nation\nConsolidated Statement of Operations\n2025 2024\nAnnual surplus $100 90\nIndependent Auditor\'s Report'}
        self.assertNotIn('unsupported_currency',identity_issues(document,[page]))
        page['text'] += '\nAmounts in US dollars'
        self.assertIn('unsupported_currency',identity_issues(document,[page]))

    def test_ocr_coordinates_keep_original_word_and_page_units(self):
        source = {'lines':[{'words':[{'text':'(1,200)','bounding_rect':{'x':250,'y':500,'width':125,'height':25}}]}]}
        self.assertEqual(ocr_words(source,2.5), [{'text':'(1,200)','x0':100,'x1':150,'top':200,'bottom':210}])

    def test_duplicate_observation_ids_are_flagged(self):
        original = deepcopy(self.records[0])
        observations, _, _, _ = resolve_observations([original, deepcopy(original)])
        self.assertTrue(all('duplicate_observation_id' in r['validationFlags'] for r in observations))
        self.assertTrue(all(r['validationStatus']=='manual_review' for r in observations))

    def test_page_evidence_is_preferred_to_an_unbacked_candidate(self):
        original = deepcopy(self.records[0])
        original['validationStatus'] = 'manual_review'
        other = deepcopy(original)
        other.update(recordId='f'*64, sourcePage=None, sourceReferences=[], sourceFiscalYear='2025-2026')
        _, canonical, _, _ = resolve_observations([other, original])
        self.assertEqual(canonical[0]['recordId'], original['recordId'])

    def test_ocr_merge_is_idempotent_for_figures_and_disclosures(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            document = {'documentKey':'one', 'bandId':'391'}
            empty = {'records':[], 'notes':[], 'entities':[], 'checks':[], 'issues':{}}
            atomic_json(root/'document-results/one.json.gz', {'document':document, 'result':deepcopy(empty)}, compressed=True)
            recovered = deepcopy(empty)
            recovered.update(records=[deepcopy(self.records[0])], notes=[{'text':'Original note'}], checks=[{'check':'example'}])
            atomic_json(root/'ocr-results/one.json.gz', {'document':document, 'status':'ocr_records_recovered', 'result':recovered}, compressed=True)
            with patch('tools.bandy_ocr_recovery.financial.safe_output_directory', return_value=root):
                self.assertEqual(merge_recoveries(root), 1)
                self.assertEqual(merge_recoveries(root), 0)
            merged = read_checkpoint(root/'document-results/one.json.gz')['result']
            self.assertEqual(len(merged['records']), 1)
            self.assertEqual(len(merged['notes']), 1)
            self.assertEqual(len(merged['checks']), 1)

    def test_export_excludes_unbacked_candidates_from_financial_queries(self):
        original = deepcopy(next(r for r in self.records if r['metric']=='cash' and not r['comparative']))
        candidate = deepcopy(original)
        candidate.update(recordId='e'*64, dimension='unbacked', sourcePage=None, sourceReferences=[],
                         validationStatus='manual_review', validationFlags=['missing_source_evidence'])
        document = {'documentKey':'one', 'bandId':original['bandId'], 'fiscalYear':original['fiscalYear']}
        manifest = {'documents':[document], 'nations':[{'bandId':original['bandId'], 'bandName':'Example', 'province':'SK', 'documentKeys':['one']}]}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            atomic_json(root/'document-results/one.json.gz', {'document':document, 'status':'extracted',
                'result':{'records':[original,candidate], 'notes':[], 'entities':[], 'checks':[], 'issues':{}}}, compressed=True)
            with patch('tools.bandy_corpus.financial.safe_output_directory', return_value=root):
                summary = finalize(root,manifest)
            self.assertEqual(summary['unbackedCandidateCount'], 1)
            self.assertEqual(summary['recordCount'], 1)
            self.assertEqual(summary['observationCount'], 2)
            with closing(sqlite3.connect(root/'export/financial.sqlite')) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM financial_records WHERE source_page IS NULL').fetchone()[0], 0)
                self.assertEqual(db.execute('SELECT COUNT(*) FROM observations').fetchone()[0], 2)


if __name__ == '__main__':
    unittest.main()
