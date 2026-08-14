import unittest

from tools.project_disclosure_extractor import parse_project_disclosures, scan_tasks


SOURCE = "https://example.test/big-river-2025.pdf"


class ProjectDisclosureExtractorTests(unittest.TestCase):
    def test_known_source_label_variants_merge_without_losing_evidence(self):
        pages = [
            "Restricted cash\nCapital project - Sewage Lagoon 1,246,169 900,000",
            "Deferred revenue\nSewage Pumping Station - ISC Capital Project 100,000 2,630,000 4,399,687 888,859",
        ]
        rows = parse_project_disclosures(
            pages,
            band_id="404",
            band_name="Big River First Nation",
            fiscal_year="2024-2025",
            source_url="https://example.test/audit.pdf",
        )
        row = next(item for item in rows if item["name"] == "Sewage Pumping Station and Lagoon")
        self.assertEqual(row["amounts"]["fundingReceived"], 2_630_000)
        self.assertEqual(row["amounts"]["restrictedCash"], 1_246_169)
        self.assertEqual(len(row["sourceReferences"]), 2)

    def test_negative_accounting_adjustments_are_not_published_as_project_amounts(self):
        pages = [
            "Deferred revenue\nBooster Station Upgrade - ISC Capital Project 0 (94,052) 0 0",
        ]
        rows = parse_project_disclosures(
            pages,
            band_id="376",
            band_name="Pheasant Rump Nakota Nation",
            fiscal_year="2020-2021",
            source_url="https://example.test/audit.pdf",
        )
        self.assertEqual(len(rows), 1)
        self.assertNotIn("fundingReceived", rows[0]["amounts"])

    def test_trivial_label_variants_do_not_create_duplicate_projects(self):
        pages = [
            "Restricted cash\nCapital project - Low Pressure Water 195,756 0\n"
            "Capital project - Water Treatment Plant Evaluation and Upgrade 248 0",
            "Deferred revenue\nWWaater Treatment Plant Evaluation and Upgrade - ISC Capital Project 99,662 0 99,662 0",
            "Recent capital projects include low pressure water project and Know Your Status project.\n"
            "Restricted cash\nCapital project - Know Your Status 198,564 0",
        ]
        rows = parse_project_disclosures(
            pages,
            band_id="404",
            band_name="Big River First Nation",
            fiscal_year="2024-2025",
            source_url="https://example.test/audit.pdf",
        )
        names = [row["name"] for row in rows]
        self.assertEqual(names.count("Low Pressure Water"), 1)
        self.assertEqual(names.count("Water Treatment Plant Evaluation and Upgrade"), 1)
        self.assertEqual(names.count("Know Your Status"), 1)

    def test_extracts_restricted_cash_and_deferred_revenue_without_inferring_status(self):
        pages = [
            """Notes to the Consolidated Financial Statements
5. Restricted cash
2025 2024
Capital project - New School Project 310,147 1,742,972
Capital project - Jet Lagoon 4,311,416 2,935,308
Capital project - 2020 Housing Renovations - 7
""",
            """9. Deferred revenue
Balance, beginning of year Amount of funding received Amount recognized as revenue Balance, end of year
New School Project - ISC Capital Project 1,748,486 - 936,964 811,522
Drainage Project - ISC Capital Project 3,229,188 1,500,000 1,656,418 3,072,770
Water Treatment Plant Evaluation and Upgrade - ISC
Capital Project 99,662 - 99,662 -
""",
        ]
        rows = parse_project_disclosures(
            pages,
            band_id="404",
            band_name="Big River First Nation",
            fiscal_year="2024-2025",
            source_url=SOURCE,
        )
        by_name = {row["name"]: row for row in rows}

        self.assertEqual(by_name["New School Project"]["amounts"]["restrictedCash"], 310147)
        self.assertEqual(by_name["New School Project"]["amounts"]["revenueRecognized"], 936964)
        self.assertEqual(by_name["Drainage Project"]["amounts"]["fundingReceived"], 1500000)
        self.assertEqual(by_name["Water Treatment Plant Evaluation and Upgrade"]["amounts"]["revenueRecognized"], 99662)
        self.assertEqual(by_name["2020 Housing Renovations"]["category"], "Housing")
        self.assertEqual(by_name["2020 Housing Renovations"]["amounts"], {})
        self.assertNotIn("status", by_name["New School Project"])

    def test_does_not_treat_generic_isc_or_program_revenue_as_projects(self):
        rows = parse_project_disclosures(
            ["""Statement of Operations
Revenue
Indigenous Services Canada - NFR Grant 32,088,626 33,661,247
Deferred Program Funding - ISC 6,876,914 14,218,759 13,741,393 7,354,280
Program expenses
Capital Projects 9,574,913 6,297,679
"""],
            band_id="404",
            band_name="Big River First Nation",
            fiscal_year="2024-2025",
            source_url=SOURCE,
        )
        self.assertEqual(rows, [])

    def test_scan_includes_manual_review_documents_but_not_non_statements(self):
        capital = {"bands": {"404": {"name": "Big River First Nation", "years": {
            "2024-2025": {"parseStatus": "parsed", "sourceUrl": "https://example.test/2025.pdf"},
            "2023-2024": {"parseStatus": "manual_review", "publishable": False, "sourceUrl": "https://example.test/2024.pdf"},
            "2022-2023": {"parseStatus": "not_applicable", "sourceUrl": "https://example.test/not-a-statement.pdf"},
        }}}}
        latest = scan_tasks(capital, all_years=False)
        all_years = scan_tasks(capital, all_years=True)
        self.assertEqual([row["fiscalYear"] for row in latest], ["2024-2025"])
        self.assertEqual([row["fiscalYear"] for row in all_years], ["2024-2025", "2023-2024"])


if __name__ == "__main__":
    unittest.main()
