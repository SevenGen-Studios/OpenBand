import unittest

from tools import layout_tables


class FakePage:
    page_number = 4
    bbox = (0, 0, 612, 792)

    def __init__(self):
        self.calls = []

    def extract_text(self, **_kwargs):
        return "Schedule of Remuneration and Expenses - Chief and Council"

    def extract_tables(self, settings=None):
        self.calls.append(settings)
        if settings is None:
            return []
        if settings.get("snap_tolerance") == 4:
            return [
                [
                    ["Name", "Position", "Months", "Remuneration", "Travel / Expenses", "Other", "Total"],
                    ["Bear, Jane", "Chief", "12", "80,000", "10,000", "", "90,000"],
                ]
            ]
        return []


class LayoutTableTests(unittest.TestCase):
    def test_falls_back_to_text_geometry_and_preserves_blank_columns(self):
        page = FakePage()
        candidates = layout_tables.extract_tables_for_page(
            page,
            page_text="Schedule of Remuneration and Expenses - Chief and Council",
            kind="remuneration",
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["strategy"], "text")
        self.assertEqual(candidates[0]["columns"], 7)
        self.assertEqual(candidates[0]["rows"][1][5], "")
        self.assertEqual(candidates[0]["page"], 4)

    def test_unrelated_table_is_not_selected_for_remuneration(self):
        class UnrelatedPage(FakePage):
            def extract_text(self, **_kwargs):
                return "Consolidated Statement of Financial Position"

            def extract_tables(self, settings=None):
                if settings is None:
                    return []
                return [[["Assets", "2025"], ["Cash", "100,000"]]]

        self.assertEqual(
            layout_tables.extract_tables_for_page(
                UnrelatedPage(), "Consolidated Statement of Financial Position", "remuneration"
            ),
            [],
        )

    def test_capital_page_texts_keep_original_page_positions(self):
        class CapitalPage(FakePage):
            def __init__(self, number, has_table):
                self.page_number = number
                self.bbox = (0, 0, 612, 792)
                self.has_table = has_table

            def extract_text(self, **_kwargs):
                return "Statement of Operations" if self.has_table else "Notes"

            def extract_tables(self, settings=None):
                if not self.has_table or settings is None:
                    return []
                return [[["Revenue", "1,000"], ["Total expenses", "800"]]]

        class FakePdf:
            pages = [CapitalPage(1, False), CapitalPage(2, True), CapitalPage(3, False)]

        pages = layout_tables.extract_table_page_texts(FakePdf(), kind="capital")
        self.assertEqual(len(pages), 3)
        self.assertEqual(pages[0], "")
        self.assertIn("Revenue 1,000", pages[1])
        self.assertEqual(pages[2], "")


if __name__ == "__main__":
    unittest.main()
