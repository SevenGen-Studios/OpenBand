"""Source-page regressions for the 2026-11-28 remuneration recovery."""
import json
from pathlib import Path
import unittest
from tools.parser_quality import validate_people
from tools.apply_manual_overrides import apply_record

ROOT = Path(__file__).resolve().parents[1]

class RecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((ROOT / 'data.json').read_text())

    def filing(self, bid, year):
        band = next(b for b in self.data['bands'] if b['id'] == bid)
        return next(f for f in band['filings'] if f['year'] == year and 'remuneration' in f['docType'].lower())

    def test_printed_fort_alexander_and_sioux_valley_footers(self):
        for bid, total, rem, expenses, count in [(262, 835259, 519692, 315567, 7), (290, 1354046, 692408, 661638, 9)]:
            filing = self.filing(bid, '2023-2024')
            self.assertEqual(len(filing['people']), count)
            self.assertEqual(sum(p['total'] for p in filing['people']), total)
            self.assertEqual(sum(p['remuneration'] for p in filing['people']), rem)
            self.assertEqual(sum(p['travel'] for p in filing['people']), expenses)
            self.assertFalse(validate_people(filing['people'], source_total=total, strict=True)['manual_review_required'])

    def test_wuskwi_other_is_not_counted_twice(self):
        row = next(p for p in self.filing(324, '2023-2024')['people'] if p['name'] == 'Nathan Kematch')
        self.assertEqual((row['remuneration'], row['travel'], row['otherPayments'], row['total']), (71500, 32150, 300, 103950))

    def test_long_plain_printed_arithmetic_difference_is_preserved(self):
        filing = self.filing(287, '2023-2024')
        row = next(p for p in filing['people'] if p['name'] == 'Kyra Wilson')
        self.assertEqual((row['remuneration'], row['travel'], row['total']), (112304, 13685, 125990))
        self.assertIn('125,990', ' '.join(filing['warnings']))
        self.assertEqual(row['reportedComponents']['salary'], 80778)
        self.assertEqual(row['reportedComponents']['vacationPayout'], 18135)

    def test_gambler_additional_roles_and_printed_differences(self):
        filing = self.filing(294, '2023-2024')
        row = next(p for p in filing['people'] if p['name'] == 'Kellie LeDoux')
        self.assertEqual(row['otherPayments'], 50935 + 9900)
        self.assertEqual(sum(p['remuneration'] + (p['otherPayments'] or 0) for p in filing['people']), 262554)
        self.assertEqual(filing['manualSourceReview']['printedColumnTotals'], {'Remuneration': 262555, 'Expenses': 15344})

    def test_source_blank_and_dash_are_retained_as_null(self):
        for bid, year, name in [(305, '2024-2025', 'Martin Nicholas'), (314, '2023-2024', 'Augustus Chartrand')]:
            row = next(p for p in self.filing(bid, year)['people'] if p['name'] == name)
            self.assertIsNone(row['travel'])
            self.assertIsNone(row['travelExpenses'])
            self.assertIsNone(row['reportedComponents']['reportedExpenses'])

    def test_reviewed_null_survives_override_replay(self):
        from tools.parser_quality import normalize_person
        row = dict(name='Source official', role='Chief', remuneration=100, travel=None, expenses=None, creditCard=None, otherPayments=None, total=100, sourceNullFields=['travel', 'otherPayments'])
        normalized = normalize_person(row)
        self.assertIsNone(normalized['travelExpenses'])
        self.assertIsNone(normalized['other'])
        self.assertEqual(normalized['total'], 100)

    def test_peguis_indirect_expenses_already_included(self):
        row = next(p for p in self.filing(269, '2019-2020')['people'] if p['name'] == 'Hudson, Glenn')
        self.assertEqual((row['remuneration'], row['travel'], row['total']), (131898, 79911, 211809))
        self.assertEqual(row['reportedComponents']['indirectExpensesIncludedInBusinessExpenses'], 25524)

    def test_protected_and_ambiguous_records_stay_unpublished(self):
        for bid, year in [(431,'2024-2025'), (309,'2023-2024'), (302,'2024-2025'), (315,'2023-2024'), (285,'2024-2025')]:
            self.assertFalse(self.filing(bid, year)['people'])

if __name__ == '__main__':
    unittest.main()
