"""Alberta identity, source matching, and conservative financial regressions."""
import hashlib
import json
import unittest
from collections import defaultdict
from pathlib import Path
from tools.ingest_alberta import canonical_url, document_identity, normalized_name, parse_filings
from tools.capital_parser import identified_revenue_fields, validate_summary, parse_page_texts
from tools.merge_previous_data import merge_band

ROOT = Path(__file__).resolve().parents[1]


class AlbertaTests(unittest.TestCase):
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
