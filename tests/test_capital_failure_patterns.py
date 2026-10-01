import unittest
from tools import capital_parser as parser


class FailurePatternTests(unittest.TestCase):
    def test_positive_reported_net_debt_is_not_net_assets(self):
        result = parser.validate_summary({"totalFinancialAssets": 100000, "totalLiabilities": 120000,
                                          "netFinancialAssetsDebt": 20000,
                                          "sourceReferences": {"netFinancialAssetsDebt": {"sourceLabel": "Net debt"}}})
        self.assertNotIn("Financial assets do not reconcile to liabilities plus net financial assets", result["warnings"])

    def test_financial_asset_reconciliation_remains_required(self):
        result = parser.validate_summary({"totalFinancialAssets": 100000, "totalLiabilities": 20000,
                                          "netFinancialAssetsDebt": 90000})
        self.assertIn("Financial assets do not reconcile to liabilities plus net financial assets", result["warnings"])

    def test_financial_asset_subtotal_is_not_all_assets(self):
        text = """Example First Nation
Consolidated Statement of Financial Position
As at March 31, 2021
2021 2020
Financial assets
Cash 100,000 90,000
Total assets 100,000 90,000
Liabilities
Total liabilities 20,000 10,000
Non-financial assets
Tangible capital assets 50,000 40,000
Total non-financial assets 50,000 40,000
Accumulated surplus 130,000 120,000
"""
        values, references = parser.extended_statement_fields([text], "2020-2021")
        self.assertIsNone(values["totalAssets"])
        self.assertEqual(values["totalFinancialAssets"], 100000)
        self.assertEqual(references["totalFinancialAssets"]["pdfPage"], 1)

    def test_trust_revenue_is_a_component_not_statement_total(self):
        text = """Example First Nation
Consolidated Statement of Financial Activities
For the year ended March 31, 2020
2020 2020 2019
Budget Actual Actual
REVENUE
Government funding 80,000 80,000 70,000
Trust Funds
Capital - 10,000 -
Revenue 5,000 5,000 4,000
Interest income - 5,000 3,000
EXPENDITURES
Education 50,000 50,000 40,000
Health 30,000 30,000 20,000
Total expenditures 80,000 80,000 60,000
EXCESS OF REVENUE OVER EXPENDITURES 5,000 20,000 17,000
"""
        result = parser.parse_page_texts([text], fiscal_year="2019-2020")
        self.assertEqual(result["totalRevenue"], 100000)
        self.assertTrue(result["publishable"], result["warnings"])

    def test_income_loss_label_preserves_reported_sign(self):
        self.assertEqual(parser.adjustment_amount("Income (loss) from enterprises", 50000), 50000)
        self.assertEqual(parser.adjustment_amount("Income (loss) from enterprises", -50000), -50000)
        self.assertEqual(parser.adjustment_amount("Loss on disposal", 50000), -50000)

    def test_revenue_subtotal_and_plain_expense_total(self):
        text = """Example First Nation
Consolidated Statement of Operations
For the year ended March 31, 2021
2021 2020
Revenue
Government grants 60,000 50,000
Health funding 20,000 10,000
Total government funding 80,000 60,000
Rental income 20,000 10,000
Total revenue 100,000 70,000
Program expenses
Education 50,000 40,000
Health 30,000 20,000
Total 80,000 60,000
Surplus 20,000 10,000
"""
        result = parser.parse_page_texts([text], fiscal_year="2020-2021")
        self.assertTrue(result["publishable"], result["warnings"])
        self.assertEqual(result["totalExpenses"], 80000)
        self.assertEqual(parser.sum_rows(result["revenueBreakdown"]), 100000)
        self.assertEqual(result["sourceReferences"]["totalExpenses"]["pdfPage"], 1)

    def test_other_items_can_include_positive_investment_earnings(self):
        text = """Consolidated Statement of Operations
2022 2022 2021
Budget Actual Actual
Program expenses
Education 100,000 100,000 90,000
Surplus from operations 1,000 7,454,371 7,380,891
Other items
Earnings from investments in Nation business entities - 18,061,979 25,888,194
Change in trust accounting estimate - 30,367 396,324
- 18,092,346 26,284,518
Surplus 1,000 25,546,717 33,665,409
"""
        self.assertEqual(parser.sum_rows(parser.parse_surplus_adjustments([text])), 18092346)

    def test_intermediate_surplus_is_not_an_adjustment(self):
        text = """Consolidated Statement of Operations
2021 2021 2020
Budget Actual Actual
Expenses
Education 100,000 100,000 90,000
Surplus before other items 9,100,793 19,220,903 6,488,252
Other income
Write off of old accounts payable - 247,993 595,736
Surplus before transfers 9,100,793 19,468,896 7,083,988
Transfers between programs
Transfers between programs 1,557,359 (922,696) -
Surplus 10,694,747 18,546,200 7,083,988
"""
        self.assertEqual(parser.sum_rows(parser.parse_surplus_adjustments([text])), -674703)

    def test_kehewin_other_revenue_and_expenditures_are_adjustments(self):
        text = """Kehewin Cree Nation
Consolidated Statement of Financial Activities
For the year ended March 31, 2024
2024 2024 2023
Budget Actual Actual
EXPENDITURES
Education 10,000 10,000 9,000
OTHER REVENUE AND EXPENDITURES
Income from investments - 902,783 679,973
Amortization - (3,256,615) (3,296,497)
- (2,353,832) (2,616,524)
EXCESS OF REVENUE OVER EXPENDITURES - 11,816,040 5,669,170
"""
        self.assertEqual(parser.sum_rows(parser.parse_surplus_adjustments([text])), -2353832)

    def test_saddle_lake_wrapped_final_surplus_with_adjustments(self):
        text = """Saddle Lake Cree Nation
Consolidated Statement of Revenues and Expenditures and Accumulated Surplus
For the Year Ended March 31, 2023
Budget
2023 2023 2022
REVENUE
Government funding 60,000 80,000 70,000
Rental income 20,000 20,000 20,000
Total revenue 80,000 100,000 90,000
EXPENDITURES
Education 40,000 50,000 45,000
Health 20,000 20,000 20,000
Total expenditures 60,000 70,000 65,000
SURPLUS FROM OPERATIONS 20,000 30,000 25,000
OTHER INCOME (EXPENSES)
Investment income - 5,000 4,000
SURPLUS OF REVENUES OVER
EXPENDITURES 20,000 35,000 29,000
"""
        result = parser.parse_page_texts([text], fiscal_year="2022-2023")
        self.assertEqual(result["annualSurplusDeficit"], 35000)
        self.assertTrue(result["publishable"], result["warnings"])

    def test_swan_river_adjustment_heading(self):
        text = """Swan River First Nation
Consolidated Statement of Financial Activities
For the year ended March 31, 2025
2025 2025 2024
Budget Actual Actual
EXPENDITURES
Education - 100,000 90,000
Other Income (Expenditures)
Share of income from First Nation
business enterprises (Note 14) - 500,611 178,171
Amortization - (1,305,333) (1,132,975)
EXCESS OF REVENUE OVER EXPENDITURES - 4,695,730 338,767
"""
        self.assertEqual(parser.sum_rows(parser.parse_surplus_adjustments([text])), -804722)

    def test_samson_carried_forward_total_is_not_a_revenue_source(self):
        text = """Samson Cree Nation
Consolidated Statement of Operations
2025 2025 2024
Budget Actual Actual
Revenue
Government funding 60,000 60,000 50,000
Rental income 40,000 40,000 30,000
Total revenue (Continued from previous page) 100,000 100,000 80,000
Program expenses
Education 50,000 50,000 40,000
Health 30,000 30,000 20,000
Total expenses 80,000 80,000 60,000
Annual surplus 20,000 20,000 20,000
"""
        result = parser.parse_page_texts([text], fiscal_year="2024-2025")
        self.assertEqual(result["totalRevenue"], 100000)
        self.assertTrue(result["publishable"], result["warnings"])

    def test_other_community_package_and_program_schedule_are_excluded(self):
        main = """First community
Consolidated Statement of Operations
For the year ended March 31, 2025
2025 2024
Revenue
Government funding 60,000 50,000
Rental income 40,000 30,000
Expenses
Education 50,000 40,000
Health 30,000 20,000
Total expenses 80,000 60,000
Annual surplus 20,000 20,000
"""
        other = main.replace("First community", "Second community").replace("20,000 20,000", "90,000 90,000")
        schedule = "First community\nStatement of Financial Activities by Program - Schedule 3\n2025 2024"
        result = parser.parse_page_texts([main, "Notes", other, schedule], fiscal_year="2024-2025")
        self.assertEqual(result["annualSurplusDeficit"], 20000)
        self.assertFalse(parser.is_primary_operations_page(schedule))

    def test_auditor_reference_is_not_statement_title(self):
        self.assertFalse(parser.is_primary_operations_page(
            "Auditor report\nstatement of operations and accumulated surplus, remeasurement gains and losses"))

    def test_numbered_company_is_an_expense_label_not_money(self):
        label, amounts = parser.line_parts("1497161 Alberta Ltd. 8 - 1,603,684 1,046,794")
        self.assertIn("1497161 Alberta Ltd", label)
        self.assertEqual(amounts, [1603684, 1046794])

    def test_wrapped_final_surplus_and_accumulated_surplus(self):
        text = "(DEFICIT)/SURPLUS OF REVENUES OVER\nEXPENDITURES (2,235,210) 14,157,451 22,576,574\nACCUMULATED SURPLUS - END OF\nYEAR 130,963,923 147,374,795 133,199,133"
        joined = parser.join_statement_labels(text)
        label, _ = parser.line_parts(joined.splitlines()[0])
        self.assertTrue(parser.FINAL_SURPLUS_RE.fullmatch(label))
        self.assertIn("ACCUMULATED SURPLUS - END OF YEAR", joined)
