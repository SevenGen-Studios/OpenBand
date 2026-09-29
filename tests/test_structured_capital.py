import unittest
from tools.capital_parser import parse_structured_capital, expand_explicit_table_rows


class StructuredCapitalTests(unittest.TestCase):
    def test_explicit_multiline_rows_preserve_labels_and_columns(self):
        rows = [["Social Services\nSpecial Projects", "2,815,058\n1,216,900", "3,045,518\n2,429,816"]]
        self.assertEqual(expand_explicit_table_rows(rows), [
            ["Social Services", "2,815,058", "3,045,518"],
            ["Special Projects", "1,216,900", "2,429,816"]])

    def test_unaligned_multiline_rows_are_not_guessed(self):
        rows = [["Social Services Special Projects", "2,815,058\n1,216,900", "3,045,518"]]
        self.assertEqual(expand_explicit_table_rows(rows), rows)

    def extraction(self):
        return {"pages": ["Cold Lake First Nations\nStatement of Operations\n2025"],
                "tables": [{"page": 1, "rows": [
                    ["", "2025", "2025 Budget", "2024"],
                    ["REVENUES", "", "", ""],
                    ["Government funding", "60", "1", "2"],
                    ["Rental income", "40", "1", "2"],
                    ["", "100", "2", "4"],
                    ["EXPENSES", "", "", ""],
                    ["Education", "50", "1", "2"],
                    ["Health", "30", "1", "2"],
                    ["", "80", "2", "4"],
                    ["OTHER INCOME", "", "", ""],
                    ["Trust income", "10", "-", "2"],
                    ["", "10", "-", "2"],
                    ["Annual surplus", "30", "-", "2"],
                ]}]}

    def test_actual_first_reconciles_with_adjustments(self):
        result = parse_structured_capital(self.extraction(), "source", "2024-2025")
        self.assertTrue(result["publishable"], result["warnings"])
        self.assertEqual(result["totalExpenses"], 80)
        self.assertEqual(result["surplusAdjustments"][0]["amount"], 10)
        self.assertEqual(result["sourceExpenseRows"][0]["sourceReference"]["columnIndex"], 1)

    def test_blank_is_not_budget_or_zero(self):
        extracted = self.extraction()
        extracted["tables"][0]["rows"][2][1] = ""
        result = parse_structured_capital(extracted, "source", "2024-2025")
        self.assertFalse(result["publishable"])
        self.assertTrue(any("Blank actual" in w for w in result["warnings"]))

    def test_merged_rows_are_blocked(self):
        extracted = self.extraction()
        extracted["tables"][0]["rows"][6][1] = "50 10"
        result = parse_structured_capital(extracted, "source", "2024-2025")
        self.assertFalse(result["publishable"])
        self.assertTrue(any("merged" in w for w in result["warnings"]))

    def test_wrong_year_is_blocked(self):
        result = parse_structured_capital(self.extraction(), "source", "2023-2024")
        self.assertFalse(result["publishable"])

    def test_multiple_tables_are_blocked(self):
        extracted = self.extraction()
        extracted["tables"] *= 2
        self.assertFalse(parse_structured_capital(extracted, "source", "2024-2025")["publishable"])
