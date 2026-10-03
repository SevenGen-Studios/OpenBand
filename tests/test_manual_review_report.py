import unittest

from tools import manual_review_report


class ManualReviewReportTests(unittest.TestCase):
    def test_alberta_manual_review_status_is_in_the_queue(self):
        report = manual_review_report.build_report({'bands': [{
            'id': 452, 'name': 'Example', 'province': 'AB', 'filings': [
                {'year': '2024-2025', 'docType': 'Schedule of Remuneration and Expenses',
                 'parse_status': 'manual_review', 'people': [], 'manual_review_required': True},
                {'year': '2023-2024', 'docType': 'Schedule of Remuneration and Expenses',
                 'parse_status': 'ok_ocr', 'manual_review_required': False}
            ]
        }]})
        self.assertEqual(report['manualReviewCount'], 1)
        self.assertEqual(report['filings'][0]['province'], 'AB')

    def test_report_includes_only_pending_manual_remuneration_filings(self):
        data = {
            "generated": "2026-06-19T00:00:00Z",
            "bands": [
                {
                    "id": 1,
                    "name": "Example First Nation",
                    "filings": [
                        {
                            "year": "2024-2025",
                            "docType": "Schedule of Remuneration and Expenses",
                            "parse_status": "pending_manual_review",
                            "href": "https://example.test/source.pdf",
                            "warnings": [
                                "Quarantined parsed rows: month values appear in money columns"
                            ],
                        },
                        {
                            "year": "2023-2024",
                            "docType": "Schedule of Remuneration and Expenses",
                            "parse_status": "ok_pdf_text",
                        },
                        {
                            "year": "2024-2025",
                            "docType": "Audited financial statements",
                            "parse_status": "pending_manual_review",
                        },
                    ],
                }
            ],
        }

        report = manual_review_report.build_report(data)

        self.assertEqual(report["manualReviewCount"], 1)
        self.assertEqual(report["filings"][0]["band"], "Example First Nation")
        self.assertEqual(
            report["filings"][0]["reason"],
            "month values appear in money columns",
        )
