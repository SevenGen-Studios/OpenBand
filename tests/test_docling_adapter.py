import os
import subprocess
import unittest
from types import SimpleNamespace
from unittest import mock

from tools import docling_adapter, capital_parser


class DoclingFallbackTests(unittest.TestCase):
    def test_raw_cells_keep_blank_columns_and_line_breaks(self):
        data = SimpleNamespace(num_rows=2, num_cols=3, table_cells=[
            SimpleNamespace(start_row_offset_idx=0, start_col_offset_idx=0, text="Label"),
            SimpleNamespace(start_row_offset_idx=1, start_col_offset_idx=0, text="Social\nProjects"),
            SimpleNamespace(start_row_offset_idx=1, start_col_offset_idx=2, text="100\n200"),
        ])
        self.assertEqual(docling_adapter.raw_table_rows(data), [
            ["Label", "", ""], ["Social\nProjects", "", "100\n200"]])

    def test_disabled_adapter_never_starts_conversion(self):
        with mock.patch.dict(os.environ, {"OPENBAND_ENABLE_DOCLING": "false"}), mock.patch.object(subprocess, "run") as run:
            self.assertEqual(docling_adapter.extract_pdf(b"pdf")["status"], "disabled")
            run.assert_not_called()

    def test_missing_dependency_is_nonfatal(self):
        with mock.patch.dict(os.environ, {"OPENBAND_ENABLE_DOCLING": "true"}), mock.patch.object(docling_adapter.importlib.util, "find_spec", return_value=None):
            result = docling_adapter.extract_pdf(b"pdf")
            self.assertEqual(result["status"], "unavailable")
            self.assertEqual(result["pages"], [])

    def test_timeout_returns_no_publishable_content(self):
        with mock.patch.dict(os.environ, {"OPENBAND_ENABLE_DOCLING": "true"}), mock.patch.object(docling_adapter.importlib.util, "find_spec", return_value=True), mock.patch.object(subprocess, "run", side_effect=subprocess.TimeoutExpired("docling", 300)):
            result = docling_adapter.extract_pdf(b"pdf")
            self.assertEqual(result["status"], "error")
            self.assertEqual(result["tables"], [])

    def test_verified_capital_skips_all_fallbacks(self):
        summary = {"publishable": True, "parseStatus": "parsed"}
        with mock.patch.object(capital_parser, "parse_pdf_bytes", return_value=summary), mock.patch.object(docling_adapter, "extract_pdf") as extract:
            result = capital_parser.parse_pdf_with_fallbacks(b"pdf")
            self.assertTrue(result["publishable"])
            extract.assert_not_called()

    def test_docling_output_still_requires_financial_validation(self):
        pending = {"publishable": False, "parseStatus": "manual_review", "warnings": []}
        page = "Statement of operations\nRevenue 100\nTotal expenses 80\nAnnual surplus 99"
        with mock.patch.object(capital_parser, "parse_pdf_bytes", return_value=pending), mock.patch.object(capital_parser.local_ocr, "ocr_pdf_bytes", return_value={"pages": []}), mock.patch.object(docling_adapter, "extract_pdf", return_value={"status": "ok", "pages": [page]}):
            result = capital_parser.parse_pdf_with_fallbacks(b"pdf", use_openai=False)
            self.assertFalse(result.get("publishable"))


if __name__ == "__main__":
    unittest.main()
