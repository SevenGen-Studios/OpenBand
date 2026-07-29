import unittest
import io
import json
import urllib.error
from pathlib import Path
from unittest import mock

from tools import capital_parser
from tools import capital_detail_enricher


class CapitalParserTests(unittest.TestCase):
    def test_openai_quota_error_stops_repeated_fallback_calls(self):
        quota_error = urllib.error.HTTPError(
            "https://api.openai.com/v1/responses",
            429,
            "quota",
            {},
            io.BytesIO(b'{"error":{"code":"insufficient_quota"}}'),
        )
        capital_parser._openai_blocked_reason = None
        try:
            with mock.patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
                with mock.patch.object(
                    capital_parser.urllib.request,
                    "urlopen",
                    side_effect=quota_error,
                ) as first_request:
                    result = capital_parser.extract_with_openai(b"pdf", "source", "2024-2025")
                self.assertEqual(result["parseStatus"], "error_openai_quota")
                self.assertEqual(first_request.call_count, 1)

                with mock.patch.object(capital_parser.urllib.request, "urlopen") as skipped_request:
                    result = capital_parser.extract_with_openai(b"pdf", "source", "2024-2025")
                self.assertEqual(result["parseStatus"], "error_openai_quota")
                skipped_request.assert_not_called()
        finally:
            capital_parser._openai_blocked_reason = None

    def test_budget_actual_prior_year_layout(self):
        pages = [
            """
            Example First Nation
            Consolidated Statement of Operations
            For the year ended March 31, 2025
            Schedules 2025 2025 2024
            Budget Actual Actual
            Revenue
            Indigenous Services Canada (Note 4) 1,000,000 2,000,000 1,800,000
            Rental income - 100,000 90,000
            Settlement 500,000 - 250,000
            Total revenue 1,500,000 2,100,000 2,140,000
            Program expenses
            Education 3 400,000 500,000 450,000
            Health 4 300,000 350,000 325,000
            Administration 5 600,000 700,000 650,000
            Total expenses 1,300,000 1,550,000 1,425,000
            Annual surplus 200,000 550,000 715,000
            """,
            """
            Example First Nation
            Consolidated Statement of Financial Position
            As at March 31, 2025
            2025 2024
            Cash resources 800,000 700,000
            Marketable securities 200,000 150,000
            Short-term debt - 25,000
            Current portion of long-term debt 50,000 45,000
            Long-term debt 450,000 475,000
            Tangible capital assets (Note 12) 4,000,000 3,500,000
            """,
            """
            Example First Nation
            Consolidated Statement of Changes in Net Financial Assets
            For the year ended March 31, 2025
            2025 2025 2024
            Budget Actual Actual
            Purchases of tangible capital assets - (600,000) (500,000)
            """,
        ]

        result = capital_parser.parse_page_texts(pages)

        self.assertEqual(result["parseStatus"], "parsed")
        self.assertEqual(result["confidence"], "high")
        self.assertEqual(result["totalRevenue"], 2100000)
        self.assertEqual(result["totalExpenses"], 1550000)
        self.assertEqual(result["annualSurplusDeficit"], 550000)
        self.assertEqual(result["cashInvestments"], 1000000)
        self.assertEqual(result["capitalSpending"]["total"], 600000)
        self.assertEqual(result["capitalAssets"], 4000000)
        self.assertEqual(result["debt"]["total"], 500000)

    def test_two_column_layout_and_negative_values(self):
        pages = [
            """
            Example First Nation
            Statement of Operations
            2024 2023
            Revenue
            Government transfer 900,000 850,000
            Investment income 100,000 80,000
            Expenses
            Education 600,000 550,000
            Operations 450,000 400,000
            Surplus (deficit) (50,000) (20,000)
            """,
            """
            Example First Nation
            Statement of Financial Position
            2024 2023
            Cash 75,000 60,000
            Long-term debt 300,000 350,000
            Tangible capital assets 2,000,000 1,800,000
            """,
            """
            Example First Nation
            Statement of Change in Net Debt
            2024 2023
            Acquisition of tangible capital assets (250,000) (200,000)
            """,
        ]

        result = capital_parser.parse_page_texts(pages)

        self.assertEqual(result["parseStatus"], "parsed")
        self.assertEqual(result["totalRevenue"], 1000000)
        self.assertEqual(result["totalExpenses"], 1050000)
        self.assertEqual(result["annualSurplusDeficit"], -50000)

    def test_budget_actual_layout_with_trailing_prior_year_dash(self):
        page = """
        Example First Nation
        Statement of Operations
        2025 2025 2024
        Budget Actual Actual
        Revenue
        Insurance proceeds 196,880 442,459 -
        CMHC - 487,662 337,715
        Total revenue 196,880 930,121 337,715
        Expenses
        Operations 100,000 800,000 300,000
        Total expenses 100,000 800,000 300,000
        Surplus 96,880 130,121 37,715
        """

        result = capital_parser.parse_page_texts([page])

        self.assertEqual(result["totalRevenue"], 930121)
        self.assertEqual(result["totalExpenses"], 800000)
        self.assertEqual(result["annualSurplusDeficit"], 130121)

    def test_plural_revenues_and_other_items_reconcile(self):
        page = """
        Example First Nation
        Consolidated Statement of Operations and Accumulated Surplus
        2025 2025 2024
        Budget Actual Actual
        Revenues
        Government funding 1,000,000 2,000,000 1,800,000
        Rental income 100,000 200,000 180,000
        Total revenues 1,100,000 2,200,000 1,980,000
        Program expenses (Schedule 2)
        Education 400,000 500,000 450,000
        Health 300,000 350,000 325,000
        Total expenses 700,000 850,000 775,000
        Surplus before other items 400,000 1,350,000 1,205,000
        Other items
        Legal settlement - (100,000) -
        Annual surplus 400,000 1,250,000 1,205,000
        """

        result = capital_parser.parse_page_texts([page])

        self.assertEqual(result["parseStatus"], "parsed")
        self.assertTrue(result["publishable"])
        self.assertEqual(result["totalRevenue"], 2200000)
        self.assertEqual(result["totalExpenses"], 850000)
        self.assertEqual(result["annualSurplusDeficit"], 1250000)
        self.assertEqual(
            result["surplusAdjustments"],
            [{"label": "Legal settlement", "amount": -100000}],
        )

    def test_unreconciled_categories_require_manual_review(self):
        summary = {
            "totalRevenue": 1000000,
            "totalExpenses": 500000,
            "annualSurplusDeficit": 500000,
            "revenueBreakdown": [{"category": "Other", "amount": 100000}],
            "expenseBreakdown": [
                {"category": "Education", "amount": 250000},
                {"category": "Health", "amount": 250000},
            ],
            "capitalSpending": None,
            "debt": None,
        }

        validation = capital_parser.validate_summary(summary)

        self.assertEqual(validation["parseStatus"], "manual_review")
        self.assertFalse(validation["publishable"])
        self.assertIn(
            "Revenue categories do not reconcile to total revenue",
            validation["warnings"],
        )

    def test_land_claims_are_not_classified_as_economic_development(self):
        self.assertEqual(
            capital_parser.broad_expense_category("Land Claims"),
            "Operations",
        )
        self.assertEqual(
            capital_parser.broad_expense_category("Land Management"),
            "Economic development",
        )

    def test_pheasant_rump_2024_2025_regression(self):
        pages = [
            """
            Pheasant Rump Nakota Nation
            Consolidated Statement of Operations
            For the year ended March 31, 2025
            Schedules 2025 2025 2024
            Budget Actual Actual
            Revenue
            Indigenous Services Canada 9,000,000 12,174,569 11,000,000
            Other revenue 4,096,432 6,925,996 5,000,000
            Total revenue 13,096,432 19,100,565 16,000,000
            Expenditures
            Community Development 3 587,752 1,625,042 2,250,342
            Economic Development 4 122,621 1,369,643 1,599,370
            Education 5 1,164,532 1,211,939 1,040,708
            Government Support 6 536,136 680,448 1,045,123
            Social Development 7 556,678 904,050 812,432
            Registration and Membership 8 5,540 5,132 5,540
            Health 9 1,148,973 1,705,013 1,274,334
            CMHC Housing 10 - 125,777 111,127
            Other Band Programs 11 2,440,359 2,684,171 1,617,653
            Total expenditures 6,562,591 10,311,215 9,756,629
            Operating surplus before other income 2,533,841 8,789,350 11,040,545
            Gain on disposal of tangible capital assets - - 20,843
            """,
            """
            Pheasant Rump Nakota Nation
            Consolidated Statement of Financial Position
            As at March 31, 2025
            2025 2024
            Cash 1,163,848 900,000
            Current portion of long-term debt 1,228,020 1,100,000
            Long-term debt 2,388,028 2,500,000
            Tangible capital assets 30,545,280 21,000,000
            """,
            """
            Pheasant Rump Nakota Nation
            Consolidated Statement of Changes in Net Financial Assets
            For the year ended March 31, 2025
            2025 2025 2024
            Budget Actual Actual
            Purchases of tangible capital assets - (9,799,376) (2,000,000)
            """,
        ]

        result = capital_parser.parse_page_texts(
            pages,
            fiscal_year="2024-2025",
        )
        expenses = {
            row["category"]: row["amount"]
            for row in result["expenseBreakdown"]
        }

        self.assertEqual(result["parseStatus"], "parsed")
        self.assertTrue(result["publishable"])
        self.assertEqual(result["totalRevenue"], 19100565)
        self.assertEqual(result["totalExpenses"], 10311215)
        self.assertEqual(result["annualSurplusDeficit"], 8789350)
        self.assertEqual(result["capitalSpending"]["total"], 9799376)
        self.assertEqual(result["capitalAssets"], 30545280)
        self.assertEqual(result["cashInvestments"], 1163848)
        self.assertEqual(result["debt"]["total"], 3616048)
        self.assertEqual(expenses["Infrastructure / public works"], 1625042)
        self.assertEqual(expenses["Economic development"], 1369643)
        self.assertEqual(expenses["Education"], 1211939)
        self.assertEqual(expenses["Administration"], 685580)
        self.assertEqual(expenses["Social programs"], 904050)
        self.assertEqual(expenses["Health"], 1705013)
        self.assertEqual(expenses["Housing"], 125777)
        self.assertEqual(expenses["Operations"], 2684171)
        self.assertEqual(sum(expenses.values()), 10311215)
        self.assertNotIn(
            "Total expenditures",
            [row["label"] for row in result["sourceExpenseRows"]],
        )

    def test_program_schedule_extracts_source_backed_expense_details(self):
        page = """
        Pheasant Rump Nakota First Nation #68
        Education
        Schedule 5 - Schedule of Revenue and Expenses
        For the year ended March 31, 2025
        2025 2025 2024
        Budget Actual Actual
        Revenue
        Indigenous Services Canada 1,164,532 1,468,777 1,229,055
        Other - 3,692 52,680
        1,164,532 1,472,469 1,281,735
        Expenses
        Salaries and benefits 396,887 324,642 336,437
        Tuition 268,410 244,589 269,219
        Transportation - 140,814 -
        Supplies 38,622 89,452 5,515
        Administration 77,523 77,523 115,124
        Amortization - 63,086 31,543
        Professional fees 84,500 55,968 101,011
        Living Allowance 65,082 35,650 64,700
        Utilities 18,500 33,617 22,267
        Student expenses 17,000 29,972 8,015
        Repairs and maintenance 30,478 22,413 21,452
        Travel 6,500 22,165 4,244
        Contracted services 8,000 21,806 3,525
        Program expense 107,238 16,169 28,835
        Insurance 1,200 12,965 2,586
        Professional development 12,000 12,834 3,826
        Telephone 3,220 4,359 2,879
        Groceries, food and meal preparation 1,500 3,494 4,640
        Meetings 9,872 395 344
        Office supplies - 26 -
        1,164,532 1,211,939 1,040,708
        Surplus - 260,530 241,027
        """

        details, schedules = capital_parser.parse_expense_detail_schedules([page])

        self.assertEqual(len(details), 20)
        self.assertEqual(
            next(row for row in details if row["label"] == "Tuition")["amount"],
            244589,
        )
        self.assertTrue(all(row["category"] == "Education" for row in details))
        self.assertNotIn(
            "Indigenous Services Canada",
            [row["label"] for row in details],
        )
        self.assertEqual(schedules[0]["reportedTotal"], 1211939)
        self.assertEqual(schedules[0]["extractedTotal"], 1211939)
        self.assertTrue(schedules[0]["reconciles"])
        self.assertEqual(schedules[0]["schedule"], "Schedule 5")
        self.assertEqual(schedules[0]["page"], 1)

    def test_expense_details_never_include_revenue_lines(self):
        page = """
        Example First Nation
        Housing
        Schedule 4 - Schedule of Revenue and Expenses
        2025 2024
        Revenue
        Government transfer 500,000 450,000
        Rental income 25,000 20,000
        Expenses
        Repairs and maintenance 100,000 90,000
        Insurance 25,000 20,000
        Total expenses 125,000 110,000
        Surplus 400,000 360,000
        """

        details, schedules = capital_parser.parse_expense_detail_schedules([page])

        self.assertEqual(
            [(row["label"], row["amount"]) for row in details],
            [("Repairs and maintenance", 100000), ("Insurance", 25000)],
        )
        self.assertNotIn("Government transfer", [row["label"] for row in details])
        self.assertNotIn("Rental income", [row["label"] for row in details])
        self.assertTrue(schedules[0]["reconciles"])

    def test_expense_details_refuse_unlabelled_non_schedule_page(self):
        page = """
        Example First Nation
        Note 12 - Commitments
        Revenue 500,000
        Expenses
        Construction project 250,000
        """

        details, schedules = capital_parser.parse_expense_detail_schedules([page])

        self.assertEqual(details, [])
        self.assertEqual(schedules, [])

    def test_detail_enrichment_requires_reconciled_existing_program_total(self):
        existing = {
            "sourceExpenseRows": [
                {"label": "Education", "category": "Education", "amount": 500000},
                {"label": "Health", "category": "Health", "amount": 300000},
            ]
        }
        parsed = {
            "expenseDetails": [
                {
                    "sourceLabel": "Education",
                    "category": "Education",
                    "label": "Tuition",
                    "amount": 500000,
                },
                {
                    "sourceLabel": "Health",
                    "category": "Health",
                    "label": "Supplies",
                    "amount": 350000,
                },
            ],
            "expenseDetailSchedules": [
                {
                    "sourceLabel": "Education",
                    "reportedTotal": 500000,
                    "reconciles": True,
                },
                {
                    "sourceLabel": "Health",
                    "reportedTotal": 350000,
                    "reconciles": True,
                },
            ],
        }

        details, schedules = capital_detail_enricher.select_safe_details(
            existing,
            parsed,
        )

        self.assertEqual([row["sourceLabel"] for row in details], ["Education"])
        self.assertEqual([row["sourceLabel"] for row in schedules], ["Education"])

    def test_revenue_value_in_expense_category_requires_manual_review(self):
        summary = {
            "totalRevenue": 19100565,
            "totalExpenses": 10311215,
            "annualSurplusDeficit": 8789350,
            "revenueBreakdown": [
                {"category": "Government transfers", "amount": 12174569},
                {"category": "Other revenue", "amount": 6925996},
            ],
            "expenseBreakdown": [
                {"category": "Operations", "amount": 19100565},
                {"category": "Education", "amount": 1211939},
            ],
            "capitalSpending": {"total": 9799376, "categories": []},
            "debt": {"total": 3616048, "components": []},
        }

        validation = capital_parser.validate_summary(summary)

        self.assertEqual(validation["parseStatus"], "manual_review")
        self.assertFalse(validation["publishable"])
        self.assertIn(
            "An expense category appears to contain total revenue",
            validation["warnings"],
        )

    def test_capital_expense_grouping_variants(self):
        self.assertEqual(
            capital_parser.broad_expense_category("CMHC Housing"),
            "Housing",
        )
        self.assertEqual(
            capital_parser.broad_expense_category("Government Services"),
            "Administration",
        )
        self.assertEqual(
            capital_parser.broad_expense_category("Registration and Membership"),
            "Administration",
        )
        self.assertEqual(
            capital_parser.broad_expense_category("Community Development"),
            "Infrastructure / public works",
        )

    def test_all_publishable_capital_records_pass_current_validation(self):
        data_path = Path(__file__).resolve().parents[1] / "capital-data.json"
        capital_data = json.loads(data_path.read_text(encoding="utf-8"))

        for band_id, band in capital_data.get("bands", {}).items():
            for fiscal_year, summary in band.get("years", {}).items():
                if (
                    summary.get("parseStatus") != "parsed"
                    or summary.get("publishable") is False
                ):
                    continue
                with self.subTest(
                    band_id=band_id,
                    band=band.get("name"),
                    fiscal_year=fiscal_year,
                ):
                    validation = capital_parser.validate_summary(summary)
                    self.assertEqual(validation["parseStatus"], "parsed")
                    self.assertTrue(validation["publishable"])


if __name__ == "__main__":
    unittest.main()
