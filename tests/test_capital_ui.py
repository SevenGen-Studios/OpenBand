import unittest
from pathlib import Path


class CapitalUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = (
            Path(__file__).resolve().parents[1] / "assets" / "openband.js"
        ).read_text(encoding="utf-8")

    def test_all_posted_audit_years_are_in_capital_selector(self):
        self.assertIn("function getCapitalAvailableYears(band)", self.script)
        self.assertIn(
            "auditedFilingsByYear(band).filter(f=>f.posted&&f.href)", self.script
        )
        self.assertIn("capitalYearStatus(band,item)", self.script)

    def test_review_state_keeps_year_selector_and_pdf_link(self):
        review_branch = self.script.split(
            "if(!summary||summary.parseStatus!=='parsed'||summary.publishable===false)", 1
        )[1].split("return}const revenue", 1)[0]
        self.assertIn("${yearControl}${capitalMemberChip(band)}", review_branch)
        self.assertIn("Review posted PDF", review_branch)


if __name__ == "__main__":
    unittest.main()
