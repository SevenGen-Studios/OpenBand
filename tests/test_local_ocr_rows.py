import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from tools.local_ocr import coordinate_lines
from tools import local_ocr


def box(x, y, width=50, height=12):
    return [[x, y], [x + width, y], [x + width, y + height], [x, y + height]]


class CoordinateRowsTests(unittest.TestCase):
    def test_later_ocr_failure_keeps_trusted_pages_and_clears_ambiguous_numbers(self):
        def render(command, **kwargs):
            Path(command[-1] + '.png').write_bytes(b'mock image')
            return SimpleNamespace(returncode=0, stderr='')
        with patch.object(local_ocr, 'availability', return_value={
                'available': True, 'pdftoppm': 'pdftoppm', 'tesseract': None, 'windows': True}), \
             patch.object(local_ocr.subprocess, 'run', side_effect=render), \
             patch.object(local_ocr, '_windows_text', side_effect=['Nation cover', 'Total Revenue 432.123']), \
             patch.object(local_ocr, '_rapidocr_text_isolated', side_effect=RuntimeError('cross-check unavailable')):
            result = local_ocr.ocr_pdf_bytes(b'%PDF-mock', page_numbers=[1, 2])
        self.assertEqual(result['status'], 'error_ocr_partial_text')
        self.assertEqual(result['pages'], ['Nation cover', ''])
        self.assertIn('cross-check unavailable', result['warnings'][0])

    def test_windows_ambiguous_thousands_separator_is_cross_checked(self):
        def render(command, **kwargs):
            Path(command[-1] + '.png').write_bytes(b'mock image')
            return SimpleNamespace(returncode=0, stderr='')
        with patch.object(local_ocr, 'availability', return_value={
                'available': True, 'pdftoppm': 'pdftoppm', 'tesseract': None, 'windows': True}), \
             patch.object(local_ocr.subprocess, 'run', side_effect=render), \
             patch.object(local_ocr, '_windows_text', return_value='Total Revenue 432.123'), \
             patch.object(local_ocr, '_rapidocr_text_isolated', return_value='Total Revenue 432,123') as cross_check:
            result = local_ocr.ocr_pdf_bytes(b'%PDF-mock', page_numbers=[1])
        self.assertEqual(result['pages'], ['Total Revenue 432,123'])
        cross_check.assert_called_once()

    def test_joined_report_headings_are_restored_without_changing_figures(self):
        text = 'ConsolidatedStatementofOperations\nTotalRevenue 1,234 (567)\nJaneBear'
        self.assertEqual(local_ocr.normalize_ocr_headings(text),
                         'Consolidated Statement of Operations\nTotal Revenue 1,234 (567)\nJaneBear')

    def test_selected_pages_keep_original_page_positions(self):
        rendered_pages = []
        def render(command, **kwargs):
            rendered_pages.append(int(command[command.index('-f') + 1]))
            Path(command[-1] + '.png').write_bytes(b'mock image')
            return SimpleNamespace(returncode=0, stderr='')
        with patch.object(local_ocr, 'availability', return_value={
                'available': True, 'pdftoppm': 'pdftoppm', 'tesseract': None}), \
             patch.object(local_ocr.subprocess, 'run', side_effect=render), \
             patch.object(local_ocr, '_rapidocr_text', side_effect=['Cover', 'Operations']):
            result = local_ocr.ocr_pdf_bytes(b'%PDF-mock', page_numbers=[1, 7])
        self.assertEqual(rendered_pages, [1, 7])
        self.assertEqual(result['pages'], ['Cover', '', '', '', '', '', 'Operations'])
        self.assertEqual(result['page_count'], 2)

    def test_recognition_can_stop_after_a_validated_statement(self):
        rendered_pages = []
        def render(command, **kwargs):
            rendered_pages.append(int(command[command.index('-f') + 1]))
            Path(command[-1] + '.png').write_bytes(b'mock image')
            return SimpleNamespace(returncode=0, stderr='')
        with patch.object(local_ocr, 'availability', return_value={
                'available': True, 'pdftoppm': 'pdftoppm', 'tesseract': None}), \
             patch.object(local_ocr.subprocess, 'run', side_effect=render), \
             patch.object(local_ocr, '_rapidocr_text', side_effect=['Cover', 'Operations']):
            result = local_ocr.ocr_pdf_bytes(b'%PDF-mock', page_numbers=[1, 7, 8, 9],
                                            stop_when=lambda pages: 'Operations' in pages)
        self.assertEqual(rendered_pages, [1, 7])
        self.assertEqual(result['page_numbers'], [1, 7])
        self.assertEqual(result['pages'][6], 'Operations')

    def test_amounts_remain_with_their_source_row(self):
        items = [(box(300, 11), "100,000"), (box(0, 10), "Education"),
                 (box(400, 10), "90,000"), (box(300, 31), "50,000"),
                 (box(0, 30), "Health")]
        self.assertEqual(coordinate_lines(items), "Education 100,000 90,000\nHealth 50,000")

    def test_wrapped_labels_do_not_merge_adjacent_rows(self):
        self.assertEqual(coordinate_lines([(box(0, 10), "Government"),
                                          (box(0, 25), "funding"),
                                          (box(300, 25), "10,000")]),
                         "Government\nfunding 10,000")

    def test_empty_result(self):
        self.assertEqual(coordinate_lines([]), "")
