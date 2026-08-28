import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import run_scraper
import scraper
from tools import local_ocr
from tools import capital_parser


OCR_SCHEDULE = """Schedule of Remuneration and Expenses - Chief and Council
Name Position Months Remuneration Travel Other Total
Jane Bear Chief 12 80,000 10,000 5,000 95,000
John Bear Councillor 12 40,000 2,000 1,000 43,000
"""

VERTICAL_OCR_SCHEDULE = """Schedule of Remuneration and Expenses
Chief and Councillors
Name
Position
Number of Months
Remuneration
Expenses
Total
Bear, Jane
Chief
12
$
80,000
$
10,000
$
90,000
Bear, John
Councillor
12
40.000
2,000
42,000
Total:
120,000
12,000
132,000
"""


class TieredPdfPipelineTests(unittest.TestCase):
    def test_vertical_ocr_cells_are_reassembled_into_official_rows(self):
        people = run_scraper._extract_people_from_text_pages([VERTICAL_OCR_SCHEDULE])

        self.assertEqual([person["name"] for person in people], ["Bear, Jane", "Bear, John"])
        self.assertEqual(people[0]["role"], "Chief")
        self.assertEqual(people[1]["remuneration"], 40000)
        self.assertEqual(people[1]["total"], 42000)

    def test_ocr_success_stops_before_openai(self):
        with mock.patch.object(run_scraper.scraper, "fetch_url", return_value=b"pdf"), mock.patch.object(
            run_scraper.scraper, "pdfplumber", None
        ), mock.patch.object(
            run_scraper.local_ocr,
            "ocr_pdf_bytes",
            return_value={"status": "ok_ocr_text", "warnings": [], "pages": [OCR_SCHEDULE]},
        ), mock.patch.object(
            run_scraper.scraper, "extract_with_openai_vision"
        ) as openai:
            result = run_scraper._extract_remuneration_rows_enhanced("https://example.test/a.pdf")

        self.assertEqual(result["parse_status"], "ok_ocr")
        self.assertEqual(len(result["people"]), 2)
        self.assertFalse(result["manual_review_required"])
        self.assertEqual([stage["stage"] for stage in result["parse_stages"]], ["local", "ocr"])
        openai.assert_not_called()

    def test_openai_runs_only_after_local_and_ocr_fail(self):
        ai_people = run_scraper._extract_people_from_text_pages([OCR_SCHEDULE])
        ai_result = {"parse_status": "ok_openai", "warnings": [], "people": ai_people}
        with mock.patch.dict(os.environ, {"OPENBAND_ALLOW_OPENAI": "true"}, clear=True), mock.patch.object(
            run_scraper.scraper, "fetch_url", return_value=b"pdf"
        ), mock.patch.object(
            run_scraper.scraper, "pdfplumber", None
        ), mock.patch.object(
            run_scraper.local_ocr,
            "ocr_pdf_bytes",
            return_value={
                "status": "skipped_ocr_unavailable",
                "warnings": ["Local OCR unavailable; missing tesseract"],
                "pages": [],
            },
        ), mock.patch.object(
            run_scraper.scraper, "extract_with_openai_vision", return_value=ai_result
        ) as openai:
            result = run_scraper._extract_remuneration_rows_enhanced("https://example.test/a.pdf")

        self.assertEqual(result["parse_status"], "ok_openai")
        self.assertEqual([stage["stage"] for stage in result["parse_stages"]], ["local", "ocr", "openai"])
        openai.assert_called_once()

    def test_missing_openai_key_is_nonfatal_and_keeps_filing_pending(self):
        with mock.patch.dict(os.environ, {"OPENBAND_ALLOW_OPENAI": "true"}, clear=True), mock.patch.object(
            run_scraper.scraper, "fetch_url", return_value=b"pdf"
        ), mock.patch.object(
            run_scraper.scraper, "pdfplumber", None
        ), mock.patch.object(
            run_scraper.local_ocr,
            "ocr_pdf_bytes",
            return_value={"status": "error_ocr_empty", "warnings": ["Local OCR returned no text"], "pages": []},
        ):
            result = run_scraper._extract_remuneration_rows_enhanced("https://example.test/a.pdf")

        self.assertEqual(result["parse_status"], "skipped_openai_no_key")
        self.assertEqual(result["people"], [])
        self.assertTrue(result["manual_review_required"])
        self.assertEqual(result["parse_stages"][-1]["stage"], "openai")

    def test_remuneration_openai_is_disabled_by_default_even_when_key_exists(self):
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "funded-key"}, clear=True), mock.patch.object(
            run_scraper.scraper, "fetch_url", return_value=b"pdf"
        ), mock.patch.object(
            run_scraper.scraper, "pdfplumber", None
        ), mock.patch.object(
            run_scraper.local_ocr,
            "ocr_pdf_bytes",
            return_value={"status": "error_ocr_empty", "warnings": [], "pages": []},
        ), mock.patch.object(
            run_scraper.scraper, "extract_with_openai_vision"
        ) as openai:
            result = run_scraper._extract_remuneration_rows_enhanced("https://example.test/a.pdf")

        self.assertEqual(result["parse_status"], "pending_openai_opt_in")
        self.assertEqual(result["parse_stages"][-1]["status"], "disabled")
        openai.assert_not_called()

    def test_capital_ocr_success_stops_before_openai(self):
        local = {
            "parseStatus": "manual_review",
            "publishable": False,
            "confidence": "low",
            "warnings": ["No totals"],
        }
        ocr = {
            "parseStatus": "parsed",
            "publishable": True,
            "confidence": "high",
            "warnings": [],
            "totalRevenue": 1000,
            "totalExpenses": 800,
            "annualSurplusDeficit": 200,
            "revenueBreakdown": [
                {"category": "Government", "amount": 700},
                {"category": "Other", "amount": 300},
            ],
            "expenseBreakdown": [
                {"category": "Education", "amount": 500},
                {"category": "Operations", "amount": 300},
            ],
        }
        with mock.patch.object(
            capital_parser, "parse_pdf_bytes", return_value=local
        ), mock.patch.object(
            capital_parser.local_ocr,
            "ocr_pdf_bytes",
            return_value={"status": "ok_ocr_text", "warnings": [], "pages": ["ocr"]},
        ), mock.patch.object(
            capital_parser, "parse_page_texts", return_value=ocr
        ), mock.patch.object(
            capital_parser, "extract_with_openai"
        ) as openai:
            result = capital_parser.parse_pdf_with_fallbacks(b"pdf")

        self.assertTrue(result["publishable"])
        self.assertEqual(result["parser"], "capital_ocr_v1")
        self.assertEqual(
            [stage["stage"] for stage in result["extractionStages"]],
            ["local", "ocr"],
        )
        openai.assert_not_called()

    def test_capital_openai_requires_explicit_opt_in(self):
        local = {
            "parseStatus": "manual_review",
            "publishable": False,
            "confidence": "low",
            "warnings": ["No totals"],
        }
        with mock.patch.object(
            capital_parser, "parse_pdf_bytes", return_value=local
        ), mock.patch.object(
            capital_parser.local_ocr,
            "ocr_pdf_bytes",
            return_value={"status": "error_ocr_empty", "warnings": [], "pages": []},
        ), mock.patch.object(
            capital_parser, "extract_with_openai"
        ) as openai:
            result = capital_parser.parse_pdf_with_fallbacks(b"pdf", use_openai=False)

        self.assertFalse(result["publishable"])
        self.assertEqual(result["extractionStages"][-1]["status"], "disabled")
        openai.assert_not_called()

    def test_successful_filing_index_only_reuses_nonempty_rows(self):
        data = {
            "bands": [
                {
                    "id": 123,
                    "filings": [
                        {"year": "2024-2025", "docType": "Schedule of Remuneration", "people": [{"name": "A"}]},
                        {"year": "2023-2024", "docType": "Schedule of Remuneration", "people": []},
                    ],
                }
            ]
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "data.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            indexed = scraper.successful_filing_index(path)

        self.assertIn(("123", "2024-2025", "schedule of remuneration"), indexed)
        self.assertNotIn(("123", "2023-2024", "schedule of remuneration"), indexed)

    def test_metrics_distinguish_each_success_tier(self):
        self.assertEqual(scraper.metric_for_result({"parse_status": "ok_pdf_text", "people": [{}]}), "local_success")
        self.assertEqual(scraper.metric_for_result({"parse_status": "ok_ocr", "people": [{}]}), "ocr_success")
        self.assertEqual(scraper.metric_for_result({"parse_status": "ok_openai", "people": [{}]}), "ai_success")
        self.assertEqual(scraper.metric_for_result({"parse_status": "skipped_openai_no_key", "people": []}), "still_pending")

    def test_ocr_adapter_reports_missing_binary(self):
        with mock.patch.object(local_ocr, "_binary", return_value=None):
            result = local_ocr.ocr_pdf_bytes(b"pdf")
        self.assertEqual(result["status"], "skipped_ocr_unavailable")
        self.assertIn("pdftoppm", result["warnings"][0])


if __name__ == "__main__":
    unittest.main()
