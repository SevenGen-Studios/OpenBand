"""Alberta identity, source matching, and conservative financial regressions."""
import hashlib
import json
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch
from collections import defaultdict
from pathlib import Path
from tools.ingest_alberta import canonical_url, document_identity, normalized_name, parse_filings, should_preserve_remuneration, update_reserve_areas
from tools.capital_parser import identified_revenue_fields, validate_summary, parse_page_texts
from tools.merge_previous_data import merge_band
from run_scraper import _build_column_map, _parse_keyword_table_row, _extract_elected_salary_schedule

ROOT = Path(__file__).resolve().parents[1]


class AlbertaTests(unittest.TestCase):
    def test_quarantined_validation_flag_is_not_a_recovered_filing(self):
        from tools.alberta_recovery_report import validated
        self.assertFalse(validated({'verificationStatus': 'automated_validated',
                                    'manual_review_required': True, 'people': []}))
        self.assertTrue(validated({'verificationStatus': 'automated_validated',
                                   'manual_review_required': False}))

    def test_worker_failure_does_not_abort_other_filings_or_mutate_shared_identity(self):
        from tools import ingest_alberta
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = {'bands': [{'id': 1, 'name': 'Example', 'aliases': ['Historic Example'],
                              'province': 'AB', 'filings': [
                {'year': '2024-2025', 'docType': 'Remuneration', 'href': 'https://example.test/fail.pdf',
                 'posted': True, 'parse_status': 'manual_review'},
                {'year': '2023-2024', 'docType': 'Remuneration', 'href': 'https://example.test/good.pdf',
                 'posted': True, 'parse_status': 'manual_review'}]}]}
            (root / 'data.json').write_text(json.dumps(data), encoding='utf-8')
            (root / 'capital-data.json').write_text('{"bands":{}}', encoding='utf-8')
            def worker(task):
                band, filing, _ = task
                band['aliases'].append('Worker-only alias')
                if 'fail.pdf' in filing['href']:
                    raise ValueError('unreadable checkpoint')
                return '1', filing['href'], {'parse_status': 'manual_review',
                                            'warnings': ['Second filing completed']}, None
            with patch.object(ingest_alberta, 'ROOT', root), \
                 patch.object(ingest_alberta, 'bounded_parse', side_effect=worker), \
                 redirect_stdout(io.StringIO()):
                ingest_alberta.parse_documents(workers=2)
            saved = ingest_alberta.read(root / 'data.json')['bands'][0]
            self.assertEqual(saved['aliases'], ['Historic Example'])
            filings = {f['year']: f for f in saved['filings']}
            self.assertIn('ValueError', filings['2024-2025']['warnings'][0])
            self.assertEqual(filings['2023-2024']['warnings'], ['Second filing completed'])

    def test_salary_honoraria_schedule_keeps_dash_columns_and_checks_footer(self):
        text = '''For Elected Officials
Months in Salary Honoraria Travel Northern Total
Office Allowance
Chief - T. Paulette 12 103,333 - - - 103,333
Councilor - K. Youngman 12 - 19,200 1,247 - 20,447
103,333 19,200 1,247 - 123,780'''
        people = _extract_elected_salary_schedule(text)
        self.assertEqual(len(people), 2)
        self.assertEqual((people[0]['remuneration'], people[0]['travel'], people[0]['total']), (103333, 0, 103333))
        self.assertEqual((people[1]['remuneration'], people[1]['travel'], people[1]['total']), (19200, 1247, 20447))
        self.assertEqual(_extract_elected_salary_schedule(text.replace('123,780', '123,781.5')), [])
        self.assertEqual(_extract_elected_salary_schedule(text.rsplit('\n', 1)[0]), [])

    def test_reserve_areas_deduplicate_parcels_and_keep_shared_identity_separate(self):
        parcel = {'number': '06640', 'hectares': '2,127.40'}
        bands = [{'id': 473, 'province': 'AB', 'iscBandNumber': 473, 'reserves': [parcel, parcel]},
                 {'id': 433, 'province': 'AB', 'iscBandNumber': 433, 'reserves': [parcel]},
                 {'id': 'ab-whitefish-lake-128', 'province': 'AB', 'sharedIscIdentity': True},
                 {'id': 344, 'province': 'SK'}]
        maps = {'communities': [{'id': b['id'], 'latitude': 50} for b in bands]}
        update_reserve_areas(bands, maps)
        row = maps['communities'][0]
        self.assertEqual((row['reserveHectares'], row['reserveParcelCount']), (2127.4, 1))
        self.assertTrue(row['reserveLandIncludesShared'])
        self.assertIn('BAND_NUMBER=473', row['reserveLandSourceUrl'])
        self.assertNotIn('reserveHectares', maps['communities'][2])
        self.assertEqual(maps['communities'][3], {'id': 344, 'latitude': 50})

    def test_bounded_parser_creates_cache_directory_before_task_write(self):
        source = (ROOT / 'tools' / 'ingest_alberta.py').read_text(encoding='utf-8')
        function = source[source.index('def bounded_parse'):source.index('def parse_documents')]
        self.assertLess(function.index('CACHE.mkdir'), function.index('write(source, task)'))

    def test_alberta_remuneration_uses_shared_table_aware_parser(self):
        source = (ROOT / 'tools' / 'ingest_alberta.py').read_text(encoding='utf-8')
        parse_one = source[source.index('def parse_one'):source.index('def bounded_parse')]
        self.assertIn('_extract_remuneration_rows_enhanced', parse_one)
        self.assertNotIn('_extract_people_from_text_pages(pages)', parse_one)

    def test_weaker_remuneration_reparse_cannot_replace_validated_rows(self):
        existing = {
            'people': [{'name': 'Chief'}, {'name': 'Councillor 1'}, {'name': 'Councillor 2'}],
            'parse_confidence': 'high',
        }
        fewer = {'people': [{'name': 'Chief'}, {'name': 'Councillor 1'}], 'parse_confidence': 'high'}
        unrelated = {
            'people': list(existing['people']),
            'parse_confidence': 'high',
            'warnings': ['Possible unrelated financial statement table'],
        }
        stronger = {'people': list(existing['people']) + [{'name': 'Councillor 3'}], 'parse_confidence': 'high'}
        self.assertTrue(should_preserve_remuneration(existing, fewer))
        self.assertTrue(should_preserve_remuneration(existing, unrelated))
        self.assertFalse(should_preserve_remuneration(existing, stronger))
        self.assertFalse(should_preserve_remuneration(
            dict(existing, sha256='old-source'), dict(fewer, sha256='revised-source')))

    def test_borderless_remuneration_columns_keep_travel_and_compensation_separate(self):
        table = [
            ['', '', '', '', 'Months', 'Band', 'Travel C', 'omps Vacation', 'Totals'],
            ['', 'Chief and', 'C', 'ouncil', '$', '$', '$', '$ $', ''],
            ['', 'Chief - Co', 'dy', 'Thomas', '12', '230,000', '1,112', '25,963', '257,075'],
            ['', 'Councillor', '-', 'Ronald V. Morin Sr.', '6', '95,972', '-', '9,688 11,509', '117,169'],
        ]
        column_map, header = _build_column_map(table)
        chief = _parse_keyword_table_row(table[2], column_map, header)
        councillor = _parse_keyword_table_row(table[3], column_map, header)
        self.assertEqual(chief['name'], 'Cody Thomas')
        self.assertEqual((chief['remuneration'], chief['travel'], chief['otherPayments'], chief['total']), (230000, 1112, 25963, 257075))
        self.assertEqual((councillor['remuneration'], councillor['travel'], councillor['otherPayments'], councillor['total']), (95972, None, 21197, 117169))

    def test_alexander_surplus_is_not_added_to_expenses(self):
        page = (ROOT/'tests/fixtures/ab_438_2025_operations.txt').read_text(encoding='utf-8')
        summary = parse_page_texts([page], fiscal_year='2024-2025')
        self.assertEqual(summary['totalRevenue'], 87170263)
        self.assertEqual(summary['totalExpenses'], 57005466)
        self.assertEqual(summary['annualSurplusDeficit'], 30164797)
        self.assertTrue(summary['publishable'])
        self.assertFalse(any('Excess' in row['label'] for row in summary['sourceExpenseRows']))

    def test_alexis_adjustment_subtotal_is_not_counted_twice(self):
        page = (ROOT/'tests/fixtures/ab_437_2025_operations.txt').read_text(encoding='utf-8')
        summary = parse_page_texts([page], fiscal_year='2024-2025')
        self.assertEqual(summary['totalRevenue'], 40815309)
        self.assertEqual(summary['totalExpenses'], 39048045)
        self.assertEqual(summary['annualSurplusDeficit'], 18394993)
        self.assertEqual(sum(r['amount'] for r in summary['surplusAdjustments']), 16627729)
        self.assertTrue(summary['publishable'])

    def test_roster_reconciles_without_umbrella_or_reserve_duplicates(self):
        roster = json.loads((ROOT / 'alberta-nations.json').read_text(encoding='utf-8'))
        data = json.loads((ROOT / 'data.json').read_text(encoding='utf-8'))['bands']
        bands = [b for b in data if b['province'] == 'AB']
        self.assertEqual(len(bands), 48)
        self.assertEqual({str(b['id']) for b in bands}, {str(b['id']) for b in roster['nations']})
        self.assertEqual(len({str(b['id']) for b in data}), len(data))
        self.assertEqual(len({normalized_name(b['name']) for b in bands}), 48)
        self.assertNotIn(471, {b['id'] for b in bands})
        by_isc = defaultdict(list)
        for band in bands:
            by_isc[band['iscBandNumber']].append(band['id'])
            self.assertIn(band['treaty'], ('Treaty 6', 'Treaty 7', 'Treaty 8'))
            self.assertTrue(any(s['field'] == 'treaty' for s in band['sources']))
        self.assertEqual({k for k,v in by_isc.items() if len(v)>1}, {462})
        self.assertEqual(set(by_isc[462]), {462, 'ab-whitefish-lake-128'})
        shared = next(b for b in bands if b.get('sharedIscIdentity'))
        self.assertFalse(shared.get('population'))
        self.assertFalse(shared.get('filings'))
        self.assertEqual(len([b for b in data if b['id'] == 344]), 1)

    def test_document_identity_and_fiscal_year_are_independent_of_listing(self):
        band = {'name':'Example First Nation','aliases':['Example Cree Nation']}
        filing = {'year':'2024-2025'}
        self.assertEqual(document_identity(['Example Cree Nation\nYear ended March 31, 2025'], band, filing), [])
        self.assertTrue(document_identity(['Unrelated First Nation March 31, 2025'], band, filing))
        self.assertTrue(document_identity(['Example First Nation March 31, 2024'], band, filing))
        self.assertTrue(document_identity([''], band, filing))

    def test_document_identity_accepts_safe_alberta_legal_name_variants(self):
        filing = {'year':'2024-2025'}
        self.assertEqual(document_identity(
            ['Enoch Cree Nation Consolidated Financial Statements March 31, 2025'],
            {'name':'Enoch Cree Nation #440','aliases':[]}, filing), [])
        self.assertEqual(document_identity(
            ['Tallcree First Nation Financial Statements for the year ended March 31, 2025'],
            {'name':'Tallcree Tribal Government','aliases':[]}, filing), [])
        self.assertEqual(document_identity(
            ['Loon River First Nation Financial Statements March 31, 2025'],
            {'name':'Loon River Cree','aliases':[]}, filing), [])

    def test_document_identity_accepts_expected_year_when_comparative_date_appears_first(self):
        issues = document_identity(
            ['Example First Nation comparative March 31, 2024; year ended March 31, 2025'],
            {'name':'Example First Nation','aliases':[]}, {'year':'2024-2025'})
        self.assertEqual(issues, [])

    def test_pdf_cover_type_can_correct_swapped_isc_labels(self):
        from tools.ingest_alberta import document_type_from_cover
        self.assertEqual(document_type_from_cover([
            "Example First Nation\nSchedule of Remuneration and Expenses\nMarch31,2025"
        ]), 'Schedule of Remuneration and Expenses')
        self.assertEqual(document_type_from_cover([
            "Example First Nation\nConsolidatedFinancialStatements\nMarch31,2025"
        ]), 'Audited consolidated financial statements')
        self.assertIsNone(document_type_from_cover(['Independent review report; ambiguous title']))
        self.assertEqual(document_type_from_cover([
            'Schedule of Chief and Council Remuneration and Expenses\n'
            'The amounts are based on the financial statements.'
        ]), 'Schedule of Remuneration and Expenses')
        self.assertIsNone(document_type_from_cover([
            'Notes to the Financial Statements\nFinancial statements are referenced here.'
        ]))

    def test_ocr_cover_accepts_joined_words_but_keeps_identity_and_year_checks(self):
        band = {'name': 'Example First Nation', 'aliases': []}
        filing = {'year': '2024-2025'}
        self.assertEqual(document_identity(['ExampleFirstNation March31,2025'], band, filing), [])
        self.assertTrue(document_identity(['UnrelatedFirstNation March31,2025'], band, filing))
        self.assertTrue(document_identity(['ExampleFirstNation March31,2024'], band, filing))

    def test_listing_omits_unposted_and_deduplicates_urls(self):
        def listing(url):
            row = f'<tr><td>2024-2025</td><td><a href="{url}">Audited consolidated financial statements</a></td><td>2026-01-01</td></tr>'
            return ('<main>Official Name Example Number 439<table>'+row+row+'<tr><td>2025-2026</td><td>Schedule of Remuneration and Expenses</td><td>Not yet posted</td></tr></table></main>').encode()
        url = 'DisplayBinaryData.aspx?BAND_NUMBER_FF=439&amp;FY=2024-2025'
        self.assertEqual(len(parse_filings(listing(url), 439)), 1)
        with self.assertRaises(ValueError):
            parse_filings(listing(url.replace('439', '440')), 439)
        with self.assertRaises(ValueError):
            parse_filings(listing(url.replace('FY=2024-2025', 'FY=2023-2024')), 439)

    def test_source_url_normalization(self):
        self.assertEqual(canonical_url('https://EXAMPLE.ca/doc?FY=2024-2025&BAND=439#page=2'), canonical_url('https://example.ca/doc?BAND=439&FY=2024-2025'))

    def test_non_isc_revenue_is_not_automatically_own_source(self):
        result = identified_revenue_fields([{'label':'Indigenous Services Canada','amount':100}, {'label':'Alberta Health','amount':30}, {'label':'Unclassified contribution','amount':70}])
        self.assertIsNone(result['ownSourceRevenue'])
        self.assertEqual(result['governmentRevenue'],130)
        self.assertEqual(result['federalGovernmentRevenue'],100)
        self.assertEqual(result['albertaGovernmentRevenue'],30)
        result = identified_revenue_fields([{'label':'Own-source revenue','amount':50}, {'label':'Rental income','amount':20}])
        self.assertEqual(result['ownSourceRevenue'],50)

    def test_unexplained_balance_difference_blocks_publication(self):
        result = validate_summary({'totalAssets':100000,'totalLiabilities':40000,'accumulatedSurplus':20000})
        self.assertFalse(result['publishable'])
        self.assertIn('Total assets do not reconcile to liabilities plus accumulated surplus',result['warnings'])

    def test_revised_pdf_cannot_inherit_old_remuneration(self):
        old = {'filings':[{'year':'2024-2025','docType':'Remuneration','href':'https://example.ca/old.pdf','people':[{'name':'Old record'}]}]}
        new = {'filings':[{'year':'2024-2025','docType':'Remuneration','href':'https://example.ca/new.pdf','people':[]}]}
        merge_band(old,new)
        self.assertEqual(new['filings'][0]['people'],[])

    def test_alberta_verified_logos_match_visual_review_hash(self):
        reviews = json.loads((ROOT/'manual_overrides/alberta-logo-reviews.json').read_text())
        bands = json.loads((ROOT/'data.json').read_text(encoding='utf-8'))['bands']
        for band in bands:
            if band['province']=='AB' and band['logo_verified']:
                payload = (ROOT/band['logo_url'].lstrip('/')).read_bytes()
                self.assertEqual(hashlib.sha256(payload).hexdigest(), reviews[str(band['id'])]['sha256'])


if __name__ == '__main__':
    unittest.main()
