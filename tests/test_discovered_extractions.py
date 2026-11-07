import unittest
from unittest.mock import patch
from tools.capital_parser import is_primary_operations_page, parse_surplus_adjustments
from tools.parse_discovered_filings import optical_evidence, money


class DiscoveredExtractionTests(unittest.TestCase):
    def test_date_caption_does_not_turn_statement_into_contents_row(self):
        self.assertTrue(is_primary_operations_page('Lucky Man Cree Nation\nStatement of Operations and Accumulated Surplus for the Year Ended March 31\n2023 2023 2022'))
        self.assertFalse(is_primary_operations_page('Contents\nStatement of Operations and Accumulated Surplus ........ 7'))
        self.assertFalse(is_primary_operations_page('Statement of Operations and Accumulated Surplus 7'))

    def test_transfers_are_explicit_adjustments_not_inferred_balancing_values(self):
        rows = parse_surplus_adjustments(['Expenses\nCurrent surplus (deficit) before transfers (1,142,573)\nTransfer to capital assets 2,272,274\nAnnual surplus 1,129,701'])
        self.assertEqual(sum(row['amount'] for row in rows), 2272274)
        self.assertEqual(parse_surplus_adjustments(['Annual surplus 1,129,701']), [])

    def test_wrapped_contribution_is_not_lost_but_distribution_remains_negative(self):
        rows = parse_surplus_adjustments(['Expenses\nAnnual surplus before other income 2,621,530\nOther income (expense)\nGain on disposal of capital assets 254,684\nContribution from trust for the purpose of per capita distributions\n(Note 20) 1,369,000\nPer capita distributions to members (1,369,000)\nAnnual surplus 2,876,214'])
        self.assertEqual(sum(row['amount'] for row in rows), 254684)
        self.assertEqual(len(rows), 3)

    def evidence(self, word):
        summary = {'fiscalYear':'2023-2024','totalRevenue':1000,'sourceReferences':{'totalRevenue':{'pdfPage':2,'table':'Statement of Operations'}}}
        rows = [{'value':1000,'reference':{'pdfPage':2,'yearValidated':True,'bbox':[0,100,500,110],'columnRight':400}}]
        return optical_evidence(summary, rows, {'pages':[{'page':2,'words':[word]}]})

    def test_matching_number_in_comparative_column_does_not_verify(self):
        word={'text':'1,000','x1':480,'top':100,'bottom':110}
        evidence, issues=self.evidence(word)
        self.assertNotIn('totalRevenue', evidence)
        word['x1']=400
        evidence, issues=self.evidence(word)
        self.assertIn('totalRevenue', evidence)
        word['text']='(1,000)'
        evidence, issues=self.evidence(word)
        self.assertNotIn('totalRevenue', evidence)

    def test_signs_and_decimal_points_are_preserved(self):
        self.assertEqual(money('($1,000.25)'), -1000.25)
        self.assertIsNone(money('1O,000'))
        self.assertNotEqual(money('1.000'),1000)

    def test_python_vision_requires_explicit_selection(self):
        from tools.local_ocr import _vision_text
        cells=[{'box':[[0,0],[100,0],[100,10],[0,10]],'text':'1,234'}]
        with patch.dict('os.environ', {'OPENBAND_VISION_PYOBJC':'1'}, clear=True), patch('tools.vision_ocr.recognize',return_value=cells):
            self.assertEqual(_vision_text('local-image.png'),'1,234')

    def test_cleanup_preserves_verified_and_review_required_audits(self):
        from tools.sanitize_data import normalize_filing_status
        digest='ab'*32
        for status in ('parsed','manual_review'):
            filing={'docType':'Audited consolidated financial statements','sha256':digest,
                    'parse_status':status,'independentVerification':{'sourceSha256':digest}}
            normalize_filing_status(filing)
            self.assertEqual(filing['parse_status'],status)
        filing={'docType':'Audited consolidated financial statements','sha256':digest,
                'parse_status':'manual_review','manual_review_required':True,
                'extractionReviewReport':'filing-extraction-report.json'}
        normalize_filing_status(filing)
        self.assertEqual(filing['parse_status'],'manual_review')
