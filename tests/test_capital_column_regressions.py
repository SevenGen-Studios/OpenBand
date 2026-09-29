import unittest

from tools import capital_parser as parser


class CapitalColumnRegressions(unittest.TestCase):
    def test_cold_lake_actual_before_budget(self):
        header = "Statement of Operations\n2025 Actual 2025 Budget 2024 Actual"
        self.assertEqual(parser.actual_value([45328903, 41719304, 46987164], header), 45328903)

    def test_montana_budget_before_actual(self):
        header = "Statement of Financial Activities\n2025 Budget 2025 Actual 2024 Actual"
        self.assertEqual(parser.actual_value([16394495, 16371157, 18173882], header), 16371157)

    def test_fort_mckay_other_items_reduce_surplus(self):
        text = """Statement of Operations
2025 Budget 2025 Actual 2024 Actual
Expenses
Education 1 2 3
Other items
Settlement Trust member distribution 1,000 18,480,000 1,000
Depreciation 1,000 7,381,814 1,000
Business profit distributions 1,000 6,320,100 1,000
Annual surplus 1,000 7,308,429 1,000
"""
        rows = parser.parse_surplus_adjustments([text])
        self.assertEqual(parser.sum_rows(rows), -32181914)

    def test_revenue_other_income_is_not_surplus_adjustment(self):
        text = "Revenues\nOther income\nRental income 100 90\nExpenses\nEducation 80 70"
        self.assertEqual(parser.parse_surplus_adjustments([text]), [])

    def test_new_extraction_missing_surplus_is_blocked(self):
        summary = {
            "requiresSurplusValidation": True,
            "totalRevenue": 100, "totalExpenses": 80,
            "revenueBreakdown": [{"amount": 50}, {"amount": 50}],
            "expenseBreakdown": [{"amount": 40}, {"amount": 40}],
        }
        result = parser.validate_summary(summary)
        self.assertFalse(result["publishable"])
