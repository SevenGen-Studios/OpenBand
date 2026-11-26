import json
import unittest
from pathlib import Path
from copy import deepcopy
from tools import capital_parser, local_ocr
from tools.apply_capital_overrides import apply_override
from tools.apply_manual_overrides import apply_record

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'research/financial-recovery/2026-11-26-blood'

class BloodFinancialRecoveryTests(unittest.TestCase):
    def test_source_ocr_continuation_final_result_is_not_an_adjustment(self):
        for year, final, adjustment in [(2024, 69646856, 8433748), (2025, 76713878, 9793598)]:
            pages = json.loads((EVIDENCE / f'blood-{year}-ocr.json').read_text())['pages']
            result = capital_parser.parse_page_texts(pages, fiscal_year=f'{year-1}-{year}')
            self.assertEqual(result['annualSurplusDeficit'], final)
            self.assertEqual([r['amount'] for r in result['surplusAdjustments']], [adjustment])
            self.assertFalse(result['publishable'], 'Unreviewed wrapped OCR rows must still fail reconciliation')

    def test_reviewed_operations_rows_and_final_adjustments_reconcile_exactly(self):
        payload = json.loads((ROOT / 'capital_overrides/2026_11_26_blood_recovery.json').read_text())
        capital = {'bands': {}}
        self.assertEqual(apply_override(capital, payload), 2)
        for year, row in capital['bands']['435']['years'].items():
            self.assertTrue(row['publishable'])
            self.assertEqual(sum(r['amount'] for r in row['sourceRevenueRows']), row['totalRevenue'])
            self.assertEqual(sum(r['amount'] for r in row['sourceExpenseRows']), row['totalExpenses'])
            self.assertEqual(row['totalRevenue'] - row['totalExpenses'] + sum(r['amount'] for r in row['surplusAdjustments']), row['annualSurplusDeficit'])
            self.assertEqual(row['sourceReferences']['annualSurplusDeficit']['pdfPage'], 8)
            broken = deepcopy(row); broken['sourceExpenseRows'][0]['amount'] += 1
            self.assertFalse(capital_parser.validate_summary(broken)['publishable'])

    def test_complete_remuneration_replay_preserves_printed_columns_and_total(self):
        payload = json.loads((ROOT / 'manual_overrides/2026_11_26_blood_2018.json').read_text())
        data = {'bands': [{'id':435, 'name':'Blood', 'filings':[{'year':'2017-2018','docType':'Schedule of Remuneration and Expenses','href':payload['sourceReviews']['2017-2018']['sourcePdf'],'people':[]}]}]}
        self.assertEqual(apply_record(data, payload), 1)
        filing = data['bands'][0]['filings'][0]
        self.assertEqual(len(filing['people']), 13)
        self.assertEqual(sum(p['total'] for p in filing['people']), 1738503)
        for person in filing['people']:
            self.assertEqual(person['remuneration'] + person['travel'], person['total'])
            cols = person['reportedColumns']
            self.assertEqual(cols['Chief and Council Travel and Per Diem'] + cols['Board Travel and Honoraria'], person['travel'])
        self.assertTrue(filing['manualSourceReview']['completeSchedule'])
        self.assertEqual(apply_record(data, payload), 0, 'Reviewed source must remain protected on replay')

    def test_explicit_department_scope_cannot_publish_as_whole_nation(self):
        text = "BLOOD TRIBE ECONOMIC DEVELOPMENT\nStatement of Operations and Accumulated Surplus\nYear ended March 31, 2023\n2023 2022\nRevenue:\nGovernment 80,000 70,000\nRent 20,000 10,000\nTotal revenue 100,000 80,000\nExpenses:\nSalaries 40,000 30,000\nTravel 20,000 10,000\nTotal expenses 60,000 40,000\nSurplus for the year 40,000 40,000"
        row = capital_parser.parse_page_texts([text], fiscal_year='2022-2023')
        self.assertTrue(row['scopeReviewRequired'])
        self.assertFalse(row['publishable'])
        self.assertIsNone(capital_parser.department_statement_scope([text.replace('BLOOD TRIBE ECONOMIC DEVELOPMENT','BLOOD TRIBE')]))
        self.assertTrue(any('Nation-wide financial scope' in w for w in row['warnings']))
        table = [['', '2023', '2022'], ['Revenue', '', ''], ['Government', '80,000', '70,000'], ['Rent', '20,000', '10,000'], ['Total revenue', '100,000', '80,000'], ['Expenses', '', ''], ['Salaries', '40,000', '30,000'], ['Travel', '20,000', '10,000'], ['Total expenses', '60,000', '40,000'], ['Surplus for the year', '40,000', '40,000']]
        structured = capital_parser.parse_structured_capital({'pages':[text], 'tables':[{'page':1, 'rows':table}]}, fiscal_year='2022-2023')
        self.assertTrue(structured['scopeReviewRequired'])
        self.assertFalse(structured['publishable'])


    def test_known_joined_headings_restore_without_altering_amounts(self):
        text = 'ConsolidatedStatementofOperationsandAccumulatedSurplus\nTotalRevenue 346,381,885'
        self.assertEqual(local_ocr.normalize_ocr_headings(text), 'Consolidated Statement of Operations and Accumulated Surplus\nTotal Revenue 346,381,885')
