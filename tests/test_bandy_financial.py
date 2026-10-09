"""Offline regressions from three actual Saskatchewan audited statements."""

from copy import deepcopy
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from tools.bandy_financial import (
    column_layout, extract_fixture, project_page, safe_output_directory,
    validate_records, write_exports,
)
from tools.capital_parser import line_parts


FIXTURES = Path(__file__).parent / "fixtures/bandy-sk"


class BandyFinancialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.documents = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))["documents"]
        cls.fixtures = {d["bandId"]: json.loads((FIXTURES / d["fixture"]).read_text(encoding="utf-8")) for d in cls.documents}
        cls.results = {bid: extract_fixture(f) for bid, f in cls.fixtures.items()}

    def scalar(self, bid, metric, year="2024-2025", result=None):
        records = (result or self.results[bid])["records"]
        rows = [r for r in records if r["metric"] == metric and r["fiscalYear"] == year]
        self.assertEqual(len(rows), 1, (bid, metric, year))
        return rows[0]

    def test_actual_current_and_comparative_totals_match_originals(self):
        expected = {
            "362": ((38959328, 38599088, 132134851), (38444446, 36119800, 2409646)),
            "391": ((39879056, 32441203, 7587853), (35668355, 32388054, 3635344)),
            "377": ((22475381, 18315827, 4159554), (17712613, 15753491, 3920324)),
        }
        for bid, years in expected.items():
            for fiscal_year, figures in zip(("2024-2025", "2023-2024"), years):
                for metric, value in zip(("totalRevenue", "totalExpenses", "annualSurplusDeficit"), figures):
                    with self.subTest(band=bid, year=fiscal_year, metric=metric):
                        row = self.scalar(bid, metric, fiscal_year)
                        self.assertEqual(row["value"], value)
                        self.assertTrue(row["sourcePage"])
                        self.assertEqual(row["comparative"], fiscal_year == "2023-2024")

    def test_additional_position_fields_match_source_pages(self):
        for bid, values in {
            "362": {"portfolioInvestments": 965, "businessInvestments": 2010276,
                    "accountsPayable": 10084241, "totalLiabilities": 107728606,
                    "currentPortionLongTermDebt": 15715196, "capitalLeaseObligations": 542451},
            "391": {"businessInvestments": 11030811, "accountsPayable": 2829899,
                    "termLoansSubjectToRefinancing": 515834, "assetRetirementObligations": 1665961},
            "377": {"guaranteedInvestmentCertificates": 3172664, "loansPayable": 667455,
                    "totalLiabilities": 20300347, "contaminatedSiteLiability": 400000,
                    "netFinancialAssetsDebt": -9960954},
        }.items():
            for metric, value in values.items():
                with self.subTest(band=bid, metric=metric):
                    self.assertEqual(self.scalar(bid, metric)["value"], value)

    def test_all_six_years_pass_strict_accounting_checks(self):
        checks = [c for result in self.results.values() for c in result["checks"]]
        self.assertEqual(len(checks), 36)
        self.assertTrue(all(c["status"] == "passed" for c in checks))
        self.assertTrue(all(abs(c["difference"]) <= 2 for c in checks))

    def test_every_record_has_original_evidence(self):
        for result in self.results.values():
            for row in result["records"]:
                self.assertTrue(row["bandId"])
                self.assertTrue(row["sourceDocument"])
                self.assertEqual(len(row["sourceDocumentSha256"]), 64)
                self.assertTrue(row["sourceReferences"])
                for ref in row["sourceReferences"]:
                    self.assertIsNotNone(ref["rawValue"])
                    self.assertEqual(str(ref["selectedYear"]), row["fiscalYear"][-4:])
                    self.assertTrue(ref["rawText"])
                    self.assertEqual(len(ref["bbox"]), 4)

    def test_budget_is_excluded_and_missing_actual_never_shifts(self):
        fixture = deepcopy(self.fixtures["362"])
        page = next(p for p in fixture["pages"] if p["page"] == 8)
        page["words"] = [w for w in page["words"] if w["text"] != "25,931,941"]
        _, rows, issue = project_page(page, "2024-2025", 2025)
        self.assertIsNone(issue)
        isc = next(r for r in rows if r["label"] == "Indigenous Services Canada")
        self.assertIsNone(isc["value"])
        result = extract_fixture(fixture)
        self.assertTrue(any(c["status"] == "failed" for c in result["checks"]))
        self.assertFalse(any(r["validationStatus"] == "machine_checked" for r in result["records"] if not r["comparative"]))

    def test_printed_dash_is_zero_and_distinct_from_blank(self):
        current = self.scalar("391", "currentCapitalLeaseObligations")
        prior = self.scalar("391", "currentCapitalLeaseObligations", "2023-2024")
        self.assertEqual(current["value"], 0)
        self.assertEqual(current["sourceReferences"][0]["rawValue"], "-")
        self.assertEqual(prior["value"], 19241)

    def test_wrong_or_ambiguous_year_headers_are_rejected(self):
        page = deepcopy(next(p for p in self.fixtures["391"]["pages"] if p["page"] == 6))
        for word in page["words"]:
            if word["text"] == "Budget":
                word["text"] = "Actual"
        columns, issue = column_layout(page, "2024-2025")
        self.assertEqual(columns, [])
        self.assertEqual(issue, "ambiguous_actual_columns")
        self.assertEqual(column_layout(page, "2030-2031")[1], "year_header_mismatch")

    def test_scaled_statements_are_quarantined(self):
        page = deepcopy(next(p for p in self.fixtures["377"]["pages"] if p["page"] == 5))
        page["text"] += "\nAmounts in thousands of dollars"
        self.assertEqual(project_page(page, "2024-2025", 2025)[2], "unsupported_scaled_units")

    def test_treaty_and_trust_numbers_are_labels(self):
        self.assertEqual(line_parts("Treaty 4 Agricultural Benefits Claim settlement proceeds 133,698,067"),
                         ("Treaty 4 Agricultural Benefits Claim settlement proceeds", [133698067.0]))
        self.assertEqual(line_parts("Land contributed by Kahkewistahaw 1907 Specific Claim"),
                         ("Land contributed by Kahkewistahaw 1907 Specific Claim", []))

    def test_nested_isc_funding_is_source_backed(self):
        row = self.scalar("391", "governmentRevenue")
        self.assertEqual(row["value"], 24970757 + 430429 + 95568)
        self.assertEqual(row["extractionBasis"], "identified_components_only")
        refs = [r for r in row["sourceReferences"] if r.get("parentLabel")]
        self.assertEqual(len(refs), 8)
        self.assertTrue(all(r["parentSource"]["sourceLabel"] == "Indigenous Services Canada" for r in refs))

    def test_accounting_inconsistency_and_missing_input_are_flagged(self):
        rows = deepcopy(self.results["391"]["records"])
        target = next(r for r in rows if r["metric"] == "totalExpenses" and not r["comparative"])
        target["value"] += 100
        checked, _ = validate_records(rows)
        self.assertTrue(all(r["validationStatus"] == "manual_review" for r in checked if not r["comparative"]))
        rows = [r for r in rows if r["metric"] != "totalLiabilities"]
        checked, checks = validate_records(rows)
        self.assertTrue(any(c["status"] == "unavailable" for c in checks))
        self.assertTrue(any("missing_check_inputs:net_financial_assets" in r["validationFlags"] for r in checked))

    def test_duplicates_and_cross_document_conflicts_are_flagged(self):
        rows = deepcopy(self.results["391"]["records"])
        rows.append(deepcopy(rows[0]))
        checked, _ = validate_records(rows)
        self.assertTrue(any("duplicate_record" in r["validationFlags"] for r in checked))
        rows[-1]["sourceDocumentSha256"] = "b" * 64
        rows[-1]["value"] += 1
        checked, _ = validate_records(rows)
        self.assertTrue(any("cross_document_conflict" in r["validationFlags"] for r in checked))

    def test_suspicious_magnitude_and_provenance_are_flagged(self):
        rows = deepcopy(self.results["391"]["records"])
        rows[0]["value"] = 20_000_000_000
        rows[0]["sourceReferences"] = []
        checked, _ = validate_records(rows)
        self.assertIn("suspicious_magnitude", checked[0]["validationFlags"])
        self.assertIn("missing_required_provenance", checked[0]["validationFlags"])

    def test_settlement_driven_spike_stays_in_review(self):
        row = self.scalar("362", "annualSurplusDeficit")
        self.assertIn("major_year_over_year_change", row["validationFlags"])
        self.assertEqual(row["validationStatus"], "manual_review")
        self.assertEqual(row["value"], 132134851)

    def test_identity_mismatch_is_quarantined(self):
        fixture = deepcopy(self.fixtures["391"])
        fixture["document"]["bandId"] = "999"
        result = extract_fixture(fixture)
        self.assertTrue(all(r["validationStatus"] == "manual_review" for r in result["records"]))
        self.assertTrue(any("source_band_identifier_mismatch" in r["validationFlags"] for r in result["records"]))

    def test_subsidiaries_are_separate_from_financial_values(self):
        result = self.results["377"]
        self.assertTrue(any("102009262 Saskatchewan" in e["entityName"] for e in result["entities"]))
        self.assertTrue(any(e["relationship"] == "portfolio_investee" for e in result["entities"]))
        self.assertTrue(all(e["validationStatus"] == "manual_review" for e in result["entities"]))
        self.assertTrue(any("claim loan" in n["text"].lower() for n in result["notes"]))

    def test_unknown_admin_expenses_stay_unavailable(self):
        self.assertFalse(any(r["metric"] == "administrativeExpenses" for result in self.results.values() for r in result["records"]))

    def test_research_exports_queryable_and_production_unchanged(self):
        original = hashlib.sha256(Path("capital-data.json").read_bytes()).hexdigest()
        allowed = safe_output_directory("research/bandy-financial")
        with tempfile.TemporaryDirectory(prefix="_test-", dir=allowed) as directory:
            output = Path(directory) / "run"
            report = write_exports(list(self.results.values()), output, self.documents)
            self.assertEqual(report["documentCount"], 3)
            self.assertEqual(report["recordCount"], 382)
            with closing(sqlite3.connect(output / "financial.sqlite")) as db:
                count = db.execute("SELECT COUNT(*) FROM checked_financial_records").fetchone()[0]
                self.assertEqual(count, report["checkedRecordCount"])
                value = db.execute("SELECT value FROM checked_financial_records WHERE band_id='377' AND fiscal_year='2024-2025' AND metric='loansPayable'").fetchone()[0]
                self.assertEqual(value, 667455)
            with self.assertRaises(FileExistsError):
                write_exports(list(self.results.values()), output, self.documents)
        self.assertEqual(hashlib.sha256(Path("capital-data.json").read_bytes()).hexdigest(), original)
        with self.assertRaises(ValueError):
            safe_output_directory("capital-data.json")


if __name__ == "__main__":
    unittest.main()
