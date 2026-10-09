import unittest

from tools import apply_manual_overrides


class ManualOverrideTests(unittest.TestCase):
    def reviewed_data(self):
        filing={'year':'2025-2026','docType':'Schedule of Remuneration and Expenses',
                'href':'https://example.org/original.pdf','sha256':'original-source',
                'people':[{'name':'Reviewed Chief','remuneration':100,'total':100}],
                'manualSourceReview':{'completeSchedule':True,'identityAndYearConfirmed':True,
                                     'sha256':'original-source','year':'2025-2026','sourcePdf':'https://example.org/original.pdf'}}
        placeholder={'year':'2025-2026','docType':filing['docType'],'posted':False,'people':[]}
        return {'bands':[{'name':'Example First Nation','filings':[placeholder,filing]}]}

    def test_legacy_override_cannot_replace_hash_bound_review(self):
        data=self.reviewed_data()
        record={'band':'Example First Nation','filings':{'2025-2026':[
            {'name':'Lower confidence Chief','remuneration':900,'total':900}]}}
        self.assertEqual(apply_manual_overrides.apply_record(data,record),0)
        self.assertEqual(data['bands'][0]['filings'][1]['people'][0]['total'],100)
        self.assertEqual(data['bands'][0]['filings'][0]['people'],[])

    def test_legacy_status_override_cannot_clear_hash_bound_review(self):
        data=self.reviewed_data()
        record={'band':'Example First Nation','filingStatuses':{'2025-2026':{'parse_status':'pending_manual_review'}}}
        self.assertEqual(apply_manual_overrides.apply_record(data,record),0)
        self.assertEqual(len(data['bands'][0]['filings'][1]['people']),1)

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
