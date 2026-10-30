import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from tools.project_disclosure_extractor import (
    add_cross_year_analysis,
    is_specific_research_lead_label,
    parse_audit_research_leads,
    parse_project_disclosures,
    scan_tasks,
    extract_one,
    disclosure_key,
    main,
)


SOURCE = "https://example.test/big-river-2025.pdf"


class ProjectDisclosureExtractorTests(unittest.TestCase):
    def test_generic_accounting_labels_are_not_research_leads(self):
        for label in (
            "Equity in tangible capital assets",
            "Equity in CMHC replacement reserve",
            "Advances to members",
            "Canada Mortgage and Housing Corporation (CMHC)",
            "Investment in Nation business entities (Note 6)",
            "Community Development Corporation",
            "Corporation",
        ):
            with self.subTest(label=label):
                self.assertFalse(is_specific_research_lead_label(label))

    def test_audit_investment_is_a_non_public_research_lead(self):
        rows = parse_audit_research_leads(
            ["""Note 8 - Investments in limited partnerships
ABC Energy Limited Partnership
4,800,000 1,200,000
Total investments 4,800,000 1,200,000"""],
            band_id="107", band_name="Cowessess First Nation",
            fiscal_year="2024-2025", source_url=SOURCE,
        )
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["originalLabel"], "ABC Energy Limited Partnership")
        self.assertEqual(row["currentYearAmount"], 4_800_000)
        self.assertEqual(row["comparativeAmount"], 1_200_000)
        self.assertEqual(row["sourceReferences"][0]["pdfPage"], 1)
        self.assertFalse(row["publishable"])
        self.assertEqual(row["researchStatus"], "pending_external_verification")

    def test_generic_totals_and_investment_income_are_not_leads(self):
        rows = parse_audit_research_leads(
            ["""Investments and business interests
Investment income 840,000 720,000
Equity in investments 991,191 889,000
Limited Partnership Earnings 103,333 90,000
Limited Partnership Interests (Note 7) 1,034,524 991,191
Holdings LP Developments LP 2025 Holdings LP Developments LP 2024
Total 4,800,000 1,200,000
Cash 1,000,000 900,000"""],
            band_id="107", band_name="Cowessess First Nation",
            fiscal_year="2024-2025", source_url=SOURCE,
        )
        self.assertEqual(rows, [])

    def test_reversed_year_columns_are_mapped_to_selected_fiscal_year(self):
        rows = parse_audit_research_leads(
            ["""Investments in limited partnerships
2024 2025
ABC Energy Limited Partnership 1,200,000 4,800,000
ABC Holdings Inc. 2024 2025"""],
            band_id="107", band_name="Cowessess First Nation",
            fiscal_year="2024-2025", source_url=SOURCE,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["currentYearAmount"], 4_800_000)
        self.assertEqual(rows[0]["comparativeAmount"], 1_200_000)

    def test_cross_year_analysis_records_changes_and_later_absence(self):
        leads = [
            {"firstNationIds": ["107"], "originalLabel": "ABC Energy LP", "fiscalYear": "2023-2024", "currentYearAmount": 1_200_000},
            {"firstNationIds": ["107"], "originalLabel": "ABC Energy LP", "fiscalYear": "2024-2025", "currentYearAmount": 6_700_000},
        ]
        add_cross_year_analysis(leads, {"107": ["2023-2024", "2024-2025", "2025-2026"]})
        self.assertEqual(leads[1]["amountChange"], 5_500_000)
        self.assertEqual(leads[1]["crossYearSignal"], "increased")
        self.assertEqual(leads[1]["notDetectedInLaterScannedYears"], ["2025-2026"])

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

    def test_alberta_deferred_schedule_recovers_named_assets_only(self):
        rows = parse_project_disclosures([
            "8. Deferred revenue\n"
            "Capital Projects: Road Upgrade - ISC 278,678 300,000 (330,084) 248,594\n"
            "Solar Power - ISC 477,326 162,900 (477,328) 162,898\n"
            "Housing - ISC 2,075,000 2,481,599 (1,174,099) 3,382,500\n"
            "Elementary and Junior High School - ISC 861,251 5,505,117 (6,366,368) -\n"
            "9. Accounts payable\nSchool construction 10,000 20,000"],
            band_id="441", band_name="Paul", fiscal_year="2025-2026", source_url=SOURCE)
        self.assertEqual({r["name"] for r in rows}, {"Capital Projects: Road Upgrade - ISC", "Solar Power - ISC"})
        for row in rows:
            self.assertEqual(row["amounts"], {})
            self.assertTrue(row["sourceReferences"][0]["originalText"])
            self.assertNotIn("status", row)

    def test_saskatchewan_coded_rows_keep_source_evidence(self):
        rows = parse_project_disclosures([
            "11. Deferred revenue\n"
            "School Renovations Project Q36Q 2,698,543 260,000 (1,740,917) 1,217,626\n"
            "Water Supply Upgrade QA3R - 300,000 - 300,000\n"
            "FN CFS - Capital Projects Q2C6 - 422,219 - 422,219\n"
            "School operations Q28P 1,000 2,000 3,000 4,000"],
            band_id="343", band_name="Mosquito", fiscal_year="2024-2025", source_url=SOURCE)
        self.assertEqual({r["name"] for r in rows}, {"School Renovations Project", "Water Supply Upgrade"})
        self.assertIn("Q36Q", rows[0]["sourceReferences"][0]["originalText"])

    def test_incidental_deferred_revenue_does_not_open_a_project_table(self):
        rows = parse_project_disclosures([
            "Statement of Operations\nDeferred revenue - prior year 100 200\n"
            "School renovation expenses 100 200\nNew school 100 200"],
            band_id="441", band_name="Paul", fiscal_year="2025-2026", source_url=SOURCE)
        self.assertEqual(rows, [])

    def test_truncated_year_label_is_not_published(self):
        rows = parse_project_disclosures([
            "9. Deferred revenue\nISC - Housing construction - Year 2 100 200 300 400"],
            band_id="354", band_name="Montreal Lake", fiscal_year="2024-2025", source_url=SOURCE)
        self.assertEqual(rows, [])

    def test_restricted_cash_uses_current_year_when_columns_are_reversed(self):
        rows = parse_project_disclosures([
            "Restricted cash\n2024 2025\nCapital project - New School 100 250"],
            band_id="404", band_name="Big River", fiscal_year="2024-2025", source_url=SOURCE)
        self.assertEqual(rows[0]["amounts"]["restrictedCash"], 250)

    def test_posted_audits_are_independent_of_capital_parser_success(self):
        roster = {"bands": [{"id": 441, "name": "Paul", "province": "AB", "filings": [
            {"year": "2025-2026", "docType": "Audited consolidated financial statements", "posted": True, "href": SOURCE},
            {"year": "2024-2025", "docType": "Schedule of Remuneration and Expenses", "posted": True, "href": SOURCE},
            {"year": "2023-2024", "docType": "Audited consolidated financial statements", "posted": False, "href": SOURCE},
        ]}]}
        capital = {"bands": {"441": {"years": {"2025-2026": {"parseStatus": "error", "sourceUrl": SOURCE}}}}}
        tasks = scan_tasks(capital, False, "AB", {"441": "AB"}, roster)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["fiscalYear"], "2025-2026")
        self.assertEqual(scan_tasks(capital, True, "SK", {"441": "AB"}, roster), [])

    def test_image_only_pdf_is_pending_ocr_not_a_successful_empty_scan(self):
        pdf = MagicMock()
        pdf.__enter__.return_value.pages = [MagicMock()]
        pdf.__enter__.return_value.pages[0].extract_text.return_value = ""
        with patch("tools.project_disclosure_extractor.fetch_pdf", return_value=b"%PDF"), patch("pdfplumber.open", return_value=pdf):
            result = extract_one({"bandId": "441", "bandName": "Paul", "fiscalYear": "2025-2026", "sourceUrl": SOURCE})
        self.assertEqual(result["status"], "needs_ocr")

    def test_separate_dollar_symbols_and_nil_columns_do_not_corrupt_names(self):
        rows = parse_project_disclosures([
            "10. Deferred revenue\n"
            "Rapid Housing - CMHC $ 1,661,281 $ - $ (162,521) $ 1,498,760"],
            band_id="468", band_name="Fort McMurray", fiscal_year="2022-2023", source_url=SOURCE)
        self.assertEqual([r["name"] for r in rows], ["Rapid Housing - CMHC"])
        self.assertEqual(rows[0]["amounts"], {})

    def test_project_code_merges_label_variants_but_program_code_does_not(self):
        rows = parse_project_disclosures([
            "7. Deferred revenue\n"
            "Green Infrastructure - New School (AT315) 10 20 30 40\n"
            "New School - AT315 (Q37U) 100 200 300 400\n"
            "Lagoon Upgrade Q37U 10 20 30 40"],
            band_id="348", band_name="Sweetgrass", fiscal_year="2025-2026", source_url=SOURCE)
        self.assertEqual(len(rows), 2)
        school = next(row for row in rows if row["category"] == "Education")
        self.assertEqual(len(school["sourceReferences"]), 2)

    def test_source_wrappers_merge_without_truncating_words(self):
        self.assertEqual(disclosure_key("SAL - Lagoon Upgrades"), disclosure_key("lagoon upgrade"))
        self.assertEqual(disclosure_key("Water disposal"), "water-disposal")

    def test_ocr_pending_run_preserves_existing_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            existing = {"id": "441-old", "firstNationIds": ["441"], "fiscalYear": "2025-2026", "name": "New school"}
            lead = {"id": "lead-441", "firstNationIds": ["441"], "fiscalYear": "2025-2026", "originalLabel": "Example LP"}
            payloads = {
                "capital": {"bands": {"441": {"years": {"2025-2026": {"parseStatus": "parsed", "sourceUrl": SOURCE}}}}},
                "data": {"bands": [{"id": 441, "name": "Paul", "province": "AB"}]},
                "projects": {"projects": [{"id": "curated-project"}], "financialDisclosures": [existing]},
                "research-leads": {"auditResearchLeads": [lead]},
            }
            args = ["extractor"]
            for key, payload in payloads.items():
                path = root / (key + ".json")
                path.write_text(json.dumps(payload))
                args.extend(["--" + key, str(path)])
            args.extend(["--report", str(root / "report.json")])
            def pending(task):
                return dict(task, status="needs_ocr", records=[], researchLeads=[])
            with patch("sys.argv", args), patch("tools.project_disclosure_extractor.extract_one", side_effect=pending):
                main()
            result = json.loads((root / "projects.json").read_text())
            self.assertEqual(result["financialDisclosures"], [existing])
            self.assertEqual(result["projects"], [{"id": "curated-project"}])
            self.assertEqual(result["financialDisclosureAudit"]["documentsNeedingOcr"], 1)
            research = json.loads((root / "research-leads.json").read_text())
            self.assertEqual(research["auditResearchLeads"], [lead])

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
