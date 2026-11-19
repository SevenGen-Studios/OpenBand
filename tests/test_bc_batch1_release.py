"""Regressions checked against the batch-one original source PDF pages."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class BCBatchOneSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.capital = json.loads((ROOT / 'capital-data.json').read_text())['bands']

    def test_osoyoos_uses_current_position_not_prior_restatement(self):
        # Osoyoos 2024-25: current statement PDF p7; prior-year note PDF p28.
        year = self.capital['596']['years']['2024-2025']
        self.assertEqual(year['cash'], 40302008)
        self.assertEqual(year['restrictedCash'], 18372632)
        self.assertEqual(year['accountsReceivable'], 3682833)
        self.assertEqual(year['cashInvestments'], 41290233)
        self.assertEqual(year['sourceReferences']['cash']['pdfPage'], 7)
        self.assertEqual(year['sourceReferences']['cash']['selectedYear'], '2025')

    def test_tlatlasikwala_comparison_interest_is_not_current_income(self):
        # 2017-18 operations PDF p6: 2,363 belongs to 2017, not 2018.
        year = self.capital['632']['years']['2017-2018']
        self.assertIsNone(year['investmentIncome'])
        self.assertEqual(year['annualSurplusDeficit'], -252074)

if __name__ == '__main__':
    unittest.main()
