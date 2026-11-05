import unittest
from unittest.mock import MagicMock, Mock, patch
from tools.recover_review_filings import candidates, usable, validate_result, windows_coordinate_ocr
from tools import ingest_alberta
from tools.parser_quality import source_total_from_table


class ReviewRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.filing = {'year': '2023-2024', 'docType': 'Audited consolidated financial statements',
                       'href': 'https://example.org/source.pdf', 'posted': True, 'sha256': 'original'}
        self.band = {'id': 123, 'name': 'Example Nation', 'province': 'SK', 'filings': [self.filing]}

    def test_capital_review_is_included_without_a_filing_flag(self):
        capital = {'bands': {'123': {'years': {'2023-2024': {'parseStatus': 'manual_review', 'publishable': False}}}}}
        self.assertEqual(len(candidates({'bands': [self.band]}, capital)), 1)
        self.assertEqual(candidates({'bands': [self.band]}, {'bands': {}}), [])

    def test_unposted_documents_are_not_recovery_candidates(self):
        self.filing.update(posted=False, manual_review_required=True)
        self.assertEqual(candidates({'bands': [self.band]}, {'bands': {}}), [])

    def test_unlabelled_footer_requires_explicit_total_column_and_no_prose(self):
        header = ['Name', 'Position', 'Months', 'Salary', 'Expenses', 'Total']
        rows = [header, ['Example Leader', 'Chief', '12', '100', '20', '120'],
                ['', '', '', '100', '20', '120']]
        self.assertEqual(source_total_from_table(rows, require_total_header=True), 120)
        self.assertIsNone(source_total_from_table(rows[:2], require_total_header=True))
        self.assertIsNone(source_total_from_table([['Name', 'Salary', 'Subtotal', 'Expenses'],
                                                  ['', '100', '100', '20']], require_total_header=True))

    def test_existing_verified_and_publishable_summaries_are_protected(self):
        for summary in [{'publishable': True}, {'manualVerified': True}, {'parser': 'manual_source_review'}]:
            self.assertTrue(usable(summary))
        self.assertFalse(usable({'parseStatus': 'manual_review', 'publishable': False}))

    def test_changed_source_cannot_inherit_validation(self):
        task = {'band': self.band, 'filing': self.filing}
        update = {'sha256': 'revised', 'httpStatus': 200, 'documentChecks': {'identityAndYearConfirmed': True},
                  'verificationStatus': 'automated_validated', 'manual_review_required': False}
        reasons = validate_result(task, ['123', self.filing['href'], update, None])
        self.assertTrue(any('digest differs' in reason for reason in reasons))

    def test_valid_statement_totals_from_unconfirmed_nation_page_are_rejected(self):
        task = {'band': self.band, 'filing': self.filing}
        refs = {name: {'pdfPage': 8, 'yearValidated': True}
                for name in ('totalRevenue', 'totalExpenses', 'annualSurplusDeficit')}
        summary = {'sourceUrl': self.filing['href'], 'fiscalYear': self.filing['year'], 'sha256': 'original',
                   'publishable': True, 'parseStatus': 'parsed', 'totalRevenue': 100, 'totalExpenses': 80,
                   'annualSurplusDeficit': 20, 'sourceReferences': refs,
                   'revenueBreakdown': [{'amount': 60}, {'amount': 40}],
                   'expenseBreakdown': [{'amount': 50}, {'amount': 30}]}
        observation = {'pdfPage': 8, 'identityConfirmed': False}
        update = {'sha256': 'original', 'httpStatus': 200, 'verificationStatus': 'automated_validated',
                  'manual_review_required': False, 'documentChecks': {'identityAndYearConfirmed': True,
                                                                     'reportedOperationsPages': [observation]}}
        result = ['123', self.filing['href'], update, summary]
        self.assertIn('Nation identity is not confirmed on every page used for reported statement totals', validate_result(task, result))
        observation['identityConfirmed'] = True
        self.assertEqual(validate_result(task, result), [])

    def test_pdfium_without_context_manager_still_closes_resources(self):
        text = Mock()
        text.get_text_range.return_value = 'Example Nation\nYear ended March 31, 2024'
        page = Mock()
        page.get_textpage.return_value = text
        document = Mock()
        document.__iter__ = Mock(return_value=iter([page]))
        pdfium = Mock()
        pdfium.PdfDocument.return_value = document
        filing = {**self.filing, 'docType': 'Other public filing'}
        with patch.dict('sys.modules', {'pypdfium2': pdfium}), patch.object(ingest_alberta, 'download', return_value=b'%PDF-test'):
            result = ingest_alberta.parse_one((self.band, filing, False))
        self.assertEqual(result[2].get('nativePageCount'), 1)
        text.close.assert_called_once()
        page.close.assert_called_once()
        document.close.assert_called_once()

    def test_coordinate_ocr_preserves_page_numbers_and_withholds_ambiguous_amounts(self):
        page = Mock()
        page.get_size.return_value = (612, 792)
        pdf = MagicMock()
        pdf.__len__.return_value = 3
        pdf.__getitem__.return_value = page
        def recognized(text):
            return {'lines': [{'words': [{'text': text, 'bounding_rect': {'x': 20, 'y': 10, 'width': 80, 'height': 15}}]}]}
        winocr = Mock()
        winocr.recognize_pil_sync.side_effect = [recognized('Example Nation'), recognized('432.123')]
        with patch.dict('sys.modules', {'pypdfium2': Mock(PdfDocument=Mock(return_value=pdf)), 'winocr': winocr}):
            result = windows_coordinate_ocr(b'%PDF-test', page_numbers=[1, 3])
        self.assertEqual(result['pages'], ['Example Nation', '', ''])
        self.assertEqual(result['page_numbers'], [1, 3])
        self.assertIn('Page 3: ambiguous OCR thousands separator', result['warnings'][0])
        pdf.close.assert_called_once()

    def test_internally_balanced_pay_rows_without_printed_footer_remain_review(self):
        filing = {**self.filing, 'docType': 'Schedule of Remuneration and Expenses'}
        update = {'sha256': 'original', 'httpStatus': 200, 'documentChecks': {'identityAndYearConfirmed': True},
                  'verificationStatus': 'automated_validated', 'manual_review_required': False,
                  'people': [{'name': 'Example Leader', 'role': 'Chief', 'months': 12,
                              'remuneration': 100, 'travelExpenses': 0, 'other': 0, 'total': 100}]}
        reasons = validate_result({'band': self.band, 'filing': filing}, ['123', filing['href'], update, None])
        self.assertIn('Complete printed schedule footer or hash-bound visual review is required', reasons)

    def test_omitted_unpaid_official_is_not_hidden_by_balanced_footer(self):
        page = ('Example Leader Chief 12 1,000 100\n'
                'Second Leader Councillor 12 1,000 100\n'
                'Third Leader Councillor 12 - -\n'
                'Total 2,000 200')
        result = {'people': [{'name': 'Example Leader'}, {'name': 'Second Leader'}], 'sourceTotal': 2200}
        self.assertIn('Parsed officials are fewer than the printed Chief and Council rows',
                      ingest_alberta.remuneration_completeness_issues(result, [[page]]))


if __name__ == '__main__':
    unittest.main()
