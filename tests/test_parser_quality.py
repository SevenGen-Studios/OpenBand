import unittest

import run_scraper
from tools import parser_quality
from tools import sanitize_data


class ParserQualityTests(unittest.TestCase):
    def parse_table(self, table, page_text="Schedule of Remuneration and Expenses - Chief and Council"):
        quality = parser_quality.score_candidate_table(table, page_text)
        people = run_scraper._extract_people_from_keyword_table(table)
        result = parser_quality.validate_people(
            people,
            source_total=parser_quality.source_total_from_table(table),
            table_quality=quality,
        )
        return quality, result

    def test_clean_standard_table(self):
        table = [
            ["Name", "Position", "Number of Months", "Remuneration", "Travel", "Expenses", "Credit Card", "Total"],
            ["Scott Eashappie", "Chief", "12", "108,791", "13,000", "256,865", "264,662", "643,318"],
            ["Shawn Spencer", "Councillor", "12", "87,000", "13,000", "84,696", "-", "184,696"],
            ["Total", "", "", "195,791", "26,000", "341,561", "264,662", "828,014"],
        ]
        quality, result = self.parse_table(table)
        self.assertTrue(quality["accepted"])
        self.assertFalse(result["manual_review_required"])
        self.assertEqual(len(result["people"]), 2)
        self.assertEqual(result["people"][0]["role"], "Chief")
        self.assertEqual(result["people"][0]["travelExpenses"], 534527)

    def test_combined_travel_expense_header(self):
        table = [
            ["Chief and Council", "Name", "Number of Months", "Remuneration", "Travel and Per Diems", "Other Payments"],
            ["Chief", "Francis X Iron", "12", "90,000", "150,465", "126,605"],
            ["Councillor", "Lorne Iron", "12", "66,000", "116,067", "67,975"],
        ]
        quality, result = self.parse_table(table)
        self.assertTrue(quality["accepted"])
        self.assertFalse(result["manual_review_required"])
        self.assertEqual(result["people"][0]["travel"], 150465)
        self.assertEqual(result["people"][0]["otherPayments"], 126605)

    def test_other_remuneration_wording(self):
        table = [
            ["Name", "Role", "Months", "Salary", "Expense reimbursement", "Other remuneration", "Total paid"],
            ["Jane Bear", "Chief", "12", "80,000", "10,000", "5,000", "95,000"],
            ["John Bear", "Councillor", "12", "40,000", "2,000", "1,000", "43,000"],
        ]
        quality, result = self.parse_table(table)
        self.assertTrue(quality["accepted"])
        self.assertEqual(result["people"][0]["remuneration"], 80000)
        self.assertEqual(result["people"][0]["expenses"], 10000)
        self.assertEqual(result["people"][0]["otherPayments"], 5000)

    def test_missing_values_do_not_create_nan(self):
        table = [
            ["Name", "Position", "Months", "Remuneration", "Travel", "Other", "Total"],
            ["Mary Stone", "Chief", "12", "75,000", "", "", "75,000"],
            ["Tom Stone", "Councillor", "6", "20,000", "-", "", "20,000"],
        ]
        _, result = self.parse_table(table)
        self.assertFalse(result["manual_review_required"])
        self.assertEqual(result["people"][0]["travelExpenses"], 0)
        self.assertEqual(result["people"][0]["other"], 0)

    def test_footer_total_row_is_not_an_official(self):
        table = [
            ["Name", "Position", "Months", "Remuneration", "Expenses", "Total"],
            ["Alice Star", "Chief", "12", "70,000", "10,000", "80,000"],
            ["Total", "", "", "70,000", "10,000", "80,000"],
        ]
        _, result = self.parse_table(table)
        self.assertEqual([p["name"] for p in result["people"]], ["Alice Star"])

    def test_wrapped_name_cell(self):
        table = [
            ["Name", "Position", "Months", "Remuneration", "Travel", "Total"],
            ["Bellegarde,\nClarence", "Chief", "12", "90,497", "77,472", "167,969"],
            ["Bellegarde,\nHolly", "Councillor", "12", "49,227", "27,348", "76,575"],
        ]
        _, result = self.parse_table(table)
        self.assertEqual(result["people"][0]["name"], "Bellegarde, Clarence")
        self.assertEqual(len(result["people"]), 2)

    def test_different_header_wording(self):
        table = [
            ["Elected Official", "Title", "Served", "Honoraria", "Allowance", "Total Paid"],
            ["Sarah Lake", "Chief", "12", "88,000", "12,000", "100,000"],
            ["Peter Lake", "Council Member", "12", "44,000", "6,000", "50,000"],
        ]
        quality, result = self.parse_table(table, "Elected officials remuneration paid expenses reimbursed")
        self.assertTrue(quality["accepted"])
        self.assertFalse(result["manual_review_required"])
        self.assertEqual(result["people"][1]["role"], "Councillor")

    def test_unrelated_financial_statement_table_is_refused(self):
        table = [
            ["Program", "Revenue", "Expenses", "Surplus"],
            ["Housing project", "100,000", "90,000", "10,000"],
            ["Administration", "50,000", "45,000", "5,000"],
        ]
        quality = parser_quality.score_candidate_table(table, "Consolidated statement of operations")
        self.assertFalse(quality["accepted"])
        result = parser_quality.validate_people([], table_quality=quality)
        self.assertTrue(result["manual_review_required"])

    def test_text_row_keeps_chief_and_combined_expense_columns(self):
        header = "Chief and Council Months Remuneration Travel and Per Diems Other Payments"
        person = run_scraper._parse_text_line(
            "Chief Francis X Iron 12 90,000 150,465 126,605",
            allow_inferred_councillor=True,
            header_context=header,
        )
        self.assertEqual(person["name"], "Francis X Iron")
        self.assertEqual(person["role"], "Chief")
        self.assertEqual(person["travel"], 150465)
        self.assertEqual(person["otherPayments"], 126605)
        self.assertEqual(person["total"], 367070)

    def test_text_row_ignores_subtotal_and_repeated_role(self):
        header = "Name Position Months Salary Other Remuneration Subtotal Expenses Total"
        self.assertTrue(
            run_scraper._is_column_header_line(
                "Name Position Months (1) Salary (2) Remuneration (3) Subtotal Expenses (4) Total"
            )
        )
        chief = run_scraper._parse_text_line(
            "Chief Erica Beaudin Chief 11 106,719 500 107,219 66,828 174,047",
            allow_inferred_councillor=True,
            header_context=header,
        )
        councillor = run_scraper._parse_text_line(
            "Gary Sparvier Councillor 1 4,690 - 4,690 72 4,762",
            allow_inferred_councillor=True,
            header_context=header,
        )
        self.assertEqual(chief["name"], "Erica Beaudin")
        self.assertEqual(chief["role"], "Chief")
        self.assertEqual(chief["remuneration"], 106719)
        self.assertEqual(chief["otherPayments"], 500)
        self.assertEqual(chief["expenses"], 66828)
        self.assertEqual(chief["total"], 174047)
        self.assertEqual(councillor["remuneration"], 4690)
        self.assertIsNone(councillor["otherPayments"])
        self.assertEqual(councillor["expenses"], 72)
        self.assertEqual(councillor["total"], 4762)

    def test_text_row_supports_parentheses_and_other_entities(self):
        header = "Other Entities Other Remuneration Months Remuneration Remuneration Expenses and Expenses"
        person = run_scraper._parse_text_line(
            "Chief Alexander (Byron) Bitternose 12 80,000 7,500 23,415 11,033",
            allow_inferred_councillor=True,
            header_context=header,
        )
        self.assertEqual(person["name"], "Alexander (Byron) Bitternose")
        self.assertEqual(person["role"], "Chief")
        self.assertEqual(person["remuneration"], 80000)
        self.assertEqual(person["expenses"], 23415)
        self.assertEqual(person["otherPayments"], 18533)
        self.assertEqual(person["total"], 121948)

    def test_text_row_repairs_split_currency_and_combines_other_remuneration(self):
        header = (
            "Piapot First Nation Piapot Piapot Cree Land First Nation Other "
            "First Nation First Nation Other Name Months Honoraria Remuneration "
            "Travel Expenses Remuneration"
        )
        person = run_scraper._parse_text_line(
            "Chief Fox, Mark 12 $ 9 0,000 125,350 36,000 6,118 7,750",
            allow_inferred_councillor=True,
            header_context=header,
        )

        self.assertEqual(person["name"], "Fox, Mark")
        self.assertEqual(person["role"], "Chief")
        self.assertEqual(person["months"], 12)
        self.assertEqual(person["remuneration"], 90000)
        self.assertEqual(person["travel"], 36000)
        self.assertEqual(person["expenses"], 6118)
        self.assertEqual(person["otherPayments"], 133100)
        self.assertEqual(person["total"], 265218)

    def test_text_row_accepts_decimal_months_and_repairs_split_expense(self):
        person = run_scraper._parse_text_line(
            "Beryl Whitecap Councillor 11.5 45,550 7 9,924 125,474",
            allow_inferred_councillor=True,
            header_context="Name Position Number of Months Remuneration Expenses Total",
        )

        self.assertEqual(person["months"], 11.5)
        self.assertEqual(person["remuneration"], 45550)
        self.assertEqual(person["travel"], 79924)
        self.assertEqual(person["total"], 125474)

    def test_text_row_uses_reported_dual_subtotals(self):
        person = run_scraper._parse_text_line(
            "Terran Keewatin Councillor 12 9 2,319 5 ,000 351 $ 97,670 1 9,411 1,560 $ 20,971",
            allow_inferred_councillor=True,
            header_context=(
                "Remuneration Expenses Name Designation Months Salary TFSA "
                "Benefits Total Travel Telephone Total"
            ),
        )

        self.assertEqual(person["remuneration"], 97670)
        self.assertEqual(person["travel"], 20971)
        self.assertEqual(person["total"], 118641)

    def test_text_row_maps_contract_billings_to_other_payments(self):
        person = run_scraper._parse_text_line(
            "Amanda Ernest Chief (Councillor for 6.5 mo.) 5.5 72,501 204,959 -",
            allow_inferred_councillor=True,
            header_context="Number of Months Remuneration Expenses Contract",
        )

        self.assertEqual(person["name"], "Amanda Ernest")
        self.assertEqual(person["role"], "Chief")
        self.assertEqual(person["months"], 5.5)
        self.assertEqual(person["remuneration"], 72501)
        self.assertEqual(person["travel"], 204959)
        self.assertIsNone(person["otherPayments"])
        self.assertEqual(person["total"], 277460)

        surname = run_scraper._parse_text_line(
            "Dale Chief Councillor 12 60,200 167,082 -",
            allow_inferred_councillor=True,
            header_context="Number of Months Remuneration Expenses Contract",
        )
        self.assertEqual(surname["name"], "Dale Chief")
        self.assertEqual(surname["role"], "Councillor")

    def test_text_pages_use_standalone_chief_section_role(self):
        people = run_scraper._extract_people_from_text_pages(
            [
                """Schedule of Remuneration and Expenses - Chief and Councillors
Name Months Honoraria Other Remuneration Travel Expenses Other Remuneration
Chief
Fox, Mark 12 $ 90,000 185,430 36,000 12,501 4,000
Councillors
Crowe, Crystal 12 $ 77,723 170,720 18,000 39,686 14,953"""
            ]
        )

        self.assertEqual(people[0]["role"], "Chief")
        self.assertEqual(people[1]["role"], "Councillor")

    def test_sanitizer_rebuilds_stale_canonical_fields_after_total_echo_repair(self):
        person = {
            "name": "Shawn Spencer",
            "role": "Councillor",
            "months": 12,
            "remuneration": 70000,
            "travel": 69862,
            "expenses": None,
            "creditCard": None,
            "otherPayments": 139862,
            "travelExpenses": 69862,
            "other": 139862,
            "total": 279724,
        }

        cleaned, status = sanitize_data.sanitize_person(person)

        self.assertEqual(status, "fixed_shifted_columns_and_total")
        self.assertEqual(cleaned["travelExpenses"], 69862)
        self.assertEqual(cleaned["other"], 0)
        self.assertEqual(cleaned["total"], 139862)

    def test_sanitizer_preserves_piapot_chief_other_remuneration(self):
        person = {
            "name": "Fox, Mark",
            "role": "Chief",
            "months": 12,
            "remuneration": 90000,
            "travel": 36000,
            "expenses": 6118,
            "creditCard": None,
            "otherPayments": 133100,
            "total": 265218,
        }

        cleaned, status = sanitize_data.sanitize_person(person)

        self.assertEqual(status, "ok")
        self.assertEqual(cleaned["otherPayments"], 133100)
        self.assertEqual(cleaned["other"], 133100)
        self.assertEqual(cleaned["travelExpenses"], 42118)
        self.assertEqual(cleaned["total"], 265218)


if __name__ == "__main__":
    unittest.main()
