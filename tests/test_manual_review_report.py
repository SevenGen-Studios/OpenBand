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


    def test_ocr_queue_prioritizes_recent_manual_review_and_requires_independent_evidence(self):
        source = 'https://example.test/source.pdf'
        digest = 'a' * 64
        base = {'docType': 'Schedule of Remuneration and Expenses', 'posted': True,
                'href': source, 'sha256': digest}
        people = [{'name': 'Example Person', 'total': 5000}]
        review = {'completeSchedule': True, 'identityAndYearConfirmed': True,
                  'sourcePdf': source, 'sha256': digest, 'sourceRowCount': 1,
                  'ocrVerification': {'engine': 'RapidOCR', 'sha256': digest}}
        report = manual_review_report.build_ocr_queue({'bands': [{
            'id': 1, 'name': 'Example Nation', 'province': 'MB', 'filings': [
                {**base, 'year': '2023-2024', 'people': people},
                {**base, 'year': '2025-2026', 'people': [], 'manual_review_required': True},
                {**base, 'year': '2024-2025', 'people': people, 'parse_status': 'ok_ocr'},
                {**base, 'year': '2022-2023', 'people': people, 'manualSourceReview': review},
                {**base, 'year': '2021-2022', 'people': people, 'manualSourceReview': review, 'sha256': 'b' * 64},
                {**base, 'year': '2020-2021', 'verificationStatus': 'wrong_document_type'},
                {**base, 'year': '2019-2020', 'posted': False},
            ],
        }]})

        self.assertEqual(report['postedFilingCount'], 6)
        self.assertEqual(report['independentlyCheckedCount'], 1)
        self.assertEqual([(row['year'], row['status']) for row in report['filings']], [
            ('2025-2026', 'manual_review'),
            ('2024-2025', 'independent_ocr_needed'),
            ('2023-2024', 'independent_ocr_needed'),
            ('2021-2022', 'independent_ocr_needed'),
            ('2020-2021', 'source_needed'),
        ])

    def test_printed_total_discrepancy_stays_in_manual_review(self):
        digest = 'a' * 64
        filing = {'docType': 'Schedule of Remuneration and Expenses', 'year': '2025-2026',
                  'posted': True, 'href': 'https://example.test/source.pdf', 'sha256': digest,
                  'people': [{'name': 'Official', 'total': 10}],
                  'manualReviewEvidence': {'sha256': digest, 'outcome': 'printed_totals_differ',
                                           'reason': 'The printed total is one dollar lower.'}}
        data = {'bands': [{'id': 1, 'name': 'Example Nation', 'province': 'AB', 'filings': [filing]}]}
        row = manual_review_report.build_ocr_queue(data)['filings'][0]
        self.assertEqual((row['status'], row['reason']),
                         ('manual_review', 'The printed total is one dollar lower.'))
        filing['manualReviewEvidence']['sha256'] = 'b' * 64
        row = manual_review_report.build_ocr_queue(data)['filings'][0]
        self.assertEqual(row['status'], 'independent_ocr_needed')
