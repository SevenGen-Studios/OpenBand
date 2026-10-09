import copy
import json
import unittest
from pathlib import Path
from tools.apply_manual_overrides import apply_record, iter_override_records
from tools.apply_capital_overrides import apply_override
from tools.sanitize_data import sanitize_filing

ROOT = Path(__file__).resolve().parents[1]


class DataAccuracyRepairsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((ROOT / 'data.json').read_text())

    def filing(self, name, year):
        band = next(b for b in self.data['bands'] if b['name'] == name)
        return next(f for f in band['filings'] if f['year'] == year and 'remuneration' in f['docType'].lower())

    def test_pbcn_source_columns_and_dashes(self):
        filing = self.filing('Peter Ballantyne Cree Nation', '2018-2019')
        rows = filing['people']
        self.assertEqual(len(rows), 22)
        # Independent column totals printed in the official schedule, PDF page 3.
        self.assertEqual([sum(p[k] for p in rows) for k in ('remuneration', 'travel', 'otherPayments', 'total')],
                         [905132, 1136759, 383684, 2425575])
        della = next(p for p in rows if p['name'] == 'Della Ballantyne')
        self.assertEqual(della['travel'], 0)
        self.assertEqual(della['total'], 9243)
        walter = next(p for p in rows if p['name'] == 'Walter Ballantyne')
        self.assertEqual(walter['otherPayments'], 7350)
        self.assertIsNone(walter['expenses'])
        self.assertTrue(any('excludes Health Services' in note for note in filing['warnings']))

    def test_wahpeton_subtotals_and_employee_pay_are_excluded(self):
        filing = self.filing('Wahpeton Dakota Nation', '2015-2016')
        rows = filing['people']
        self.assertEqual([sum(p[k] for p in rows) for k in ('remuneration', 'travel', 'otherPayments', 'total')],
                         [62600, 15000, 3000, 80600])
        self.assertEqual(sum(p['employmentDisclosure']['total'] for p in rows), 111785)
        for person in rows:
            self.assertIsNone(person['creditCard'])
            self.assertFalse(person['employmentDisclosure']['includedInCouncilTotal'])
            self.assertEqual(person['total'], person['remuneration'] + person['travel'] + person['otherPayments'])
        self.assertEqual(next(p for p in rows if p['name'] == 'John Waditaka')['total'], 15300)

    def test_overrides_replay_without_losing_source_scope_notes(self):
        before = copy.deepcopy(self.data)
        data = copy.deepcopy(self.data)
        records = list(iter_override_records(ROOT / 'manual_overrides/2026_10_09_data_accuracy_repairs.json'))
        for record in records:
            self.assertEqual(apply_record(data, record), 1)
        self.assertEqual(data, before)
        for record in records:
            for people in record['filings'].values():
                for person in people:
                    self.assertTrue(person['sourceReference']['yearValidated'])
                    self.assertEqual(len(person['sourceReference']['sourceDocumentSha256']), 64)

    def test_carry_the_kettle_credit_card_digits_and_source_rounding(self):
        older = self.filing('Carry the Kettle Nakoda Nation', '2021-2022')
        chief = next(p for p in older['people'] if p['role'] == 'Chief')
        self.assertEqual(chief['creditCard'], 268981)
        self.assertEqual(chief['total'], 877349)
        self.assertEqual(sum(p['total'] for p in older['people']), 2018217)
        newer = self.filing('Carry the Kettle Nakoda Nation', '2023-2024')
        chief = next(p for p in newer['people'] if p['role'] == 'Chief')
        self.assertEqual(chief['creditCard'], 136245)
        self.assertEqual(chief['total'], 370408)
        self.assertEqual(sum(p['total'] for p in newer['people']), 1469161)
        self.assertTrue(any('rounded rows' in note for note in newer['warnings']))

    def test_cowessess_subtotal_is_not_an_additional_payment(self):
        filing = self.filing('Cowessess First Nation', '2013-2014')
        self.assertEqual(len(filing['people']), 16)
        self.assertEqual(sum(p['remuneration'] for p in filing['people']), 393743)
        self.assertEqual(sum(p['travel'] for p in filing['people']), 234161)
        self.assertEqual(sum(p['total'] for p in filing['people']), 627904)
        chief = next(p for p in filing['people'] if p['name'] == 'Terrence Lavallee')
        self.assertEqual(chief['otherPayments'], 0)
        self.assertEqual(chief['total'], 133448)
        for person in filing['people']:
            self.assertEqual(person['totalBasis'], 'derived_sum')
            self.assertEqual(person['total'], person['reportedRemunerationSubtotal'] + person['travel'])

    def test_source_reviewed_rows_survive_the_scraper_sanitizer(self):
        records = list(iter_override_records(ROOT / 'manual_overrides/2026_10_09_data_accuracy_repairs.json'))
        for record in records:
            for year in record['filings']:
                with self.subTest(band=record['band'], year=year):
                    filing = copy.deepcopy(self.filing(record['band'], year))
                    before = copy.deepcopy(filing)
                    self.assertEqual(sanitize_filing(filing), (len(filing['people']), 0, 0))
                    self.assertEqual(filing, before)

    def test_flying_dust_negative_expense_reconciles_to_reported_totals(self):
        capital = json.loads((ROOT / 'capital-data.json').read_text())
        summary = capital['bands']['395']['years']['2024-2025']
        row = next(r for r in summary['sourceExpenseRows'] if r['label'] == 'Flying Dust Property Tax Program')
        self.assertEqual(row['amount'], -1356)
        self.assertEqual(summary['totalExpenses'], 31013641)
        self.assertEqual(sum(r['amount'] for r in summary['sourceExpenseRows']), 31013641)
        self.assertEqual(sum(r['amount'] for r in summary['expenseBreakdown']), 31013641)
        self.assertEqual(summary['totalRevenue'] - summary['totalExpenses'] + sum(r['amount'] for r in summary['surplusAdjustments']), summary['annualSurplusDeficit'])
        before = copy.deepcopy(summary)
        payload = json.loads((ROOT / 'capital_overrides/2026_10_09_flying_dust_expenses.json').read_text())
        self.assertEqual(apply_override(capital, payload), 1)
        self.assertEqual(capital['bands']['395']['years']['2024-2025'], before)
        # A correction to selected fields must not assert that every other
        # value in the summary was independently manually verified.
        self.assertEqual(summary.get('manualVerified'), before.get('manualVerified'))
        absent = {'bands': {}}
        with self.assertRaisesRegex(ValueError, 'no existing summary'):
            apply_override(absent, payload)


if __name__ == '__main__':
    unittest.main()
