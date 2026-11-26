import json
import tempfile
import unittest
from pathlib import Path
from tools.audit_financial_coverage import inventory

class FinancialCoverageAuditTests(unittest.TestCase):
    def test_unknown_source_availability_is_distinct_from_posted_extraction_holds(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'data.json').write_text(json.dumps({'bands':[{'id':1,'name':'Nation','province':'AB','filings':[
                {'year':'2024-2025','docType':'Audited financial statements','posted':True,'href':'https://example.test/audit.pdf'},
                {'year':'2023-2024','docType':'Schedule of Remuneration and Expenses','posted':True,'href':'https://example.test/pay.pdf','people':[]},
                {'year':'2022-2023','docType':'Audited financial statements','posted':False,'href':None}]}]}))
            (root/'capital-data.json').write_text('{"bands":{}}')
            result = inventory(root)
            rows = {(r['year'],r['kind']):r for r in result['communities'][0]['filings']}
            self.assertEqual(rows['2024-2025','capital']['state'],'posted_without_summary')
            self.assertEqual(rows['2023-2024','remuneration']['state'],'posted_without_rows')
            self.assertEqual(rows['2022-2023','capital']['state'],'not_indexed_as_posted')
            self.assertEqual(rows['2024-2025','remuneration']['state'],'not_indexed_unknown_availability')
            self.assertIsNone(rows['2024-2025','remuneration']['sourceUrl'])
