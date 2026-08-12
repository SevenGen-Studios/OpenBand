import unittest

from tools import apply_manual_overrides


class ManualOverrideTests(unittest.TestCase):
    def test_status_override_labels_wrong_source_document_without_rows(self):
        data = {
            "bands": [
                {
                    "name": "Example First Nation",
                    "filings": [
                        {
                            "year": "2024-2025",
                            "docType": "Schedule of Remuneration and Expenses",
                            "people": [],
                            "parse_status": "pending_openai_opt_in",
                        }
                    ],
                }
            ]
        }
        record = {
            "band": "Example First Nation",
            "source": "Official source",
            "filingStatuses": {
                "2024-2025": {
                    "parse_status": "not_applicable_wrong_document",
                    "warnings": ["Official link contains a different document"],
                }
            },
        }

        applied = apply_manual_overrides.apply_record(data, record)
        filing = data["bands"][0]["filings"][0]

        self.assertEqual(applied, 1)
        self.assertEqual(filing["parse_status"], "not_applicable_wrong_document")
        self.assertFalse(filing["manual_review_required"])
        self.assertEqual(filing["people"], [])
        self.assertTrue(filing["manual_override"])


if __name__ == "__main__":
    unittest.main()
