"""Source-derived regression: Cowessess's 2023 operations statement, PDF p8."""
import copy
import hashlib
import json
import unittest
from pathlib import Path
from tools.capital_parser import line_parts, actual_value, parse_page_texts, validate_summary
from tools.audit_capital_classification import audit_dataset, disclosure_coverage

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'research/classification-audit/2026-11-02/sources/cowessess-financial-2022-2023.pdf'


class SourceAuditTests(unittest.TestCase):
    def test_nested_numeric_disclosure_is_label_not_amount(self):
        line = 'FSIN (net of deferred revenue of $1,800,000 (2022 - nil)) - (412,859) 604,046'
        label, values = line_parts(line)
        self.assertIn('$1,800,000 (2022 - nil)', label)
        self.assertEqual(values, [-412859, 604046])
        self.assertEqual(actual_value(values, '2023 2023 2022\nBudget', line), -412859)
        self.assertEqual(line_parts('Other (412,859) 604,046'), ('Other', [-412859, 604046]))

    def test_original_statement_revenue_reconciles_but_ambiguous_adjustments_stay_held(self):
        # Read original native text rather than a synthetic replacement statement.
        import pdfplumber
        with pdfplumber.open(SOURCE) as pdf:
            pages = [page.extract_text() or '' for page in pdf.pages[:10]]
        result = parse_page_texts(pages, fiscal_year='2022-2023')
        row = next(r for r in result['sourceRevenueRows'] if r['label'].startswith('FSIN'))
        self.assertEqual(row['amount'], -412859)
        self.assertEqual(row['category'], 'Unclassified')
        self.assertEqual(sum(r['amount'] for r in result['sourceRevenueRows']), 44440344)
        self.assertEqual(result['totalRevenue'], 44440344)
        self.assertEqual(result['totalExpenses'], 32671475)
        # The source heading says Other expense above positive gains. A fresh
        # extraction must stay held until those adjustment signs are reviewed.
        self.assertFalse(result['publishable'])
        self.assertIn('Revenue, expenses, and annual surplus do not reconcile', result['warnings'])

    def test_persisted_correction_preserves_totals_and_source_hash(self):
        s = json.loads((ROOT/'capital-data.json').read_text())['bands']['361']['years']['2022-2023']
        r = next(r for r in s['sourceRevenueRows'] if r['label'].startswith('FSIN'))
        self.assertEqual(r['amount'], -412859)
        self.assertEqual(r['sourceReview']['pdfSha256'], hashlib.sha256(SOURCE.read_bytes()).hexdigest())
        self.assertEqual(sum(r['amount'] for r in s['sourceRevenueRows']), s['totalRevenue'])
        self.assertEqual(sum(r['amount'] for r in s['revenueBreakdown']), s['totalRevenue'])
        self.assertEqual(s['totalRevenue'], 44440344)
        self.assertEqual(s['annualSurplusDeficit'], 15268997)
        self.assertTrue(s['publishable'])
        # Operations program called Capital is separate from asset acquisitions.
        self.assertEqual(next(r['amount'] for r in s['sourceExpenseRows'] if r['label']=='Capital'),2255511)
        self.assertEqual(s['capitalSpending']['total'],6276524)

    def test_wrong_columns_cannot_pass_despite_reconciled_totals(self):
        base = json.loads((ROOT/'capital-data.json').read_text())['bands']['361']['years']['2022-2023']
        for location in ['sourceExpenseRows', 'sourceRevenueRows', 'sourceReferences']:
            for bad in [{'selectedYear':'2022'}, {'selectedColumn':'budget'}, {'fiscalYear':'2021-2022'}]:
                with self.subTest(location=location,bad=bad):
                    s=copy.deepcopy(base)
                    if location=='sourceReferences':
                        ref=s.setdefault(location,{}).setdefault('totalRevenue',{})
                    else:
                        ref=s[location][0]['sourceReference']
                    ref.update(bad)
                    self.assertFalse(validate_summary(s)['publishable'])

    def test_disclosure_absence_is_separate_from_pending_extraction(self):
        inventory={'bands':[dict(id=999,iscBandNumber=361,province='SK',filings=[
            dict(docType='Audited financial statements',year='2022-2023',posted=True,href='pdf'),
            dict(docType='Audited financial statements',year='2023-2024',posted=False),
            dict(docType='Remuneration',year='2022-2023',posted=True,href='schedule')])]}
        c=disclosure_coverage({'bands':{}},inventory)
        self.assertEqual(c['postedWithoutSummary'],1)
        self.assertEqual(c['notPostedOrLinkUnavailable'],1)
        self.assertEqual(c['indexedAuditedFilings'],2)
        inventory['bands'][0]['filings'].append(dict(docType='Audited financial statements',year='2022-2023',posted=True,href='second-index-entry'))
        c=disclosure_coverage({'bands':{}},inventory)
        self.assertEqual(c['postedAuditedFilings'],1)
        self.assertEqual(c['duplicateIndexedNationYears'],1)

    def test_synthetic_application_id_is_not_an_isc_band_number(self):
        s=dict(parseStatus='parsed',publishable=True,sourceRevenueRows=[dict(label='Other',amount=100,category='Other revenue')],sourceUrl='https://example.com/?BAND_NUMBER_FF=361')
        report=audit_dataset({'bands':{'999':{'name':'Nation','years':{'2022-2023':s}}}}, {'bands':[dict(id=999,iscBandNumber=361,province='SK')]})
        self.assertNotIn('Source URL belongs to another Nation',report['rows'][0]['issues'])
