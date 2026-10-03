import unittest
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from tools.local_ocr import coordinate_lines
from tools import local_ocr


def box(x, y, width=50, height=12):
    return [[x, y], [x + width, y], [x + width, y + height], [x, y + height]]


class CoordinateRowsTests(unittest.TestCase):
    def test_financial_position_blank_actual_cash_keeps_the_prior_amount_out(self):
        from tools.capital_parser import parse_page_texts
        items = [(box(10,0,330),'Statement of Financial Position'),
                 (box(200,20),'2025'), (box(300,20),'2024'),
                 (box(10,40),'Cash'), (box(300,40),'500'),
                 (box(10,60),'Investments'), (box(200,60),'100'), (box(300,60),'200'),
                 (box(10,80),'Accounts receivable'), (box(200,80),'300'), (box(300,80),'400'),
                 (box(10,100),'Total financial assets'), (box(200,100),'400'), (box(300,100),'1,100')]
        recognized = coordinate_lines(items, True, True)
        self.assertTrue(recognized['financialColumnsAligned'])
        self.assertIn('Cash - 500', recognized['text'])
        operations = 'Statement of Operations\n2025 2024\nRevenue\nIndigenous Services Canada 80 70\nRental income 20 10\nTotal revenue 100 80\nExpenses\nEducation 50 40\nHealth 30 20\nTotal expenses 80 60\nAnnual surplus 20 20'
        result = parse_page_texts([operations, recognized['text']], fiscal_year='2024-2025', require_reported_totals=True)
        self.assertTrue(result['publishable'], result['warnings'])
        self.assertEqual(result['cashInvestments'], 100)

    def test_schedule_indices_and_small_actual_amounts_keep_their_columns(self):
        from tools.capital_parser import parse_page_texts
        items = json.loads((Path(__file__).parent/'fixtures'/'ab_446_2022_ocr_boxes.json').read_text(encoding='utf8'))
        recognized = coordinate_lines([(box,text) for box,text,confidence in items], True, True)
        self.assertTrue(recognized['financialColumnsAligned'])
        text = local_ocr.normalize_ocr_headings(recognized['text'])
        self.assertIn('Investment income 46 187', text)
        self.assertIn('C-92 Capacity Funding 79,227 -', text)
        self.assertIn('Treaty8FirstNationsofAlberta - 222,304', text)
        result = parse_page_texts(['']*8+[text], fiscal_year='2021-2022', require_reported_totals=True)
        self.assertTrue(result['publishable'], result['warnings'])
        self.assertEqual(result['totalRevenue'], 26129301)
        self.assertEqual(result['totalExpenses'], 25790087)
        self.assertEqual(result['annualSurplusDeficit'], -710793)
        self.assertEqual(result['sourceReferences']['totalRevenue']['pdfPage'], 9)
        changed = text.replace('Investment income 46 187','Investment income 187 46')
        self.assertFalse(parse_page_texts(['']*8+[changed], fiscal_year='2021-2022', require_reported_totals=True)['publishable'])

    def test_actual_columns_and_reported_footer_reconcile_in_fort_mckay_scan(self):
        from tools.capital_parser import parse_page_texts
        items = json.loads((Path(__file__).parent/'fixtures'/'ab_467_2025_ocr_boxes.json').read_text(encoding='utf8'))
        text = local_ocr.normalize_ocr_headings(coordinate_lines(
            [(box,text) for box,text,confidence in items], align_financial_columns=True))
        self.assertIn('First Nations Development Funding 682,399 - 2,289,544', text)
        self.assertIn('Investment income - 3,281,283 7,414,371', text)
        result = parse_page_texts(['']*5+[text], fiscal_year='2024-2025', require_reported_totals=True)
        self.assertTrue(result['publishable'], result['warnings'])
        self.assertEqual(result['totalRevenue'],111781540)
        self.assertEqual(result['totalExpenses'],72291197)
        self.assertEqual(result['annualSurplusDeficit'],7308429)
        self.assertEqual(result['sourceReferences']['totalRevenue']['pdfPage'],6)
        result.update(requiresAlignedColumns=True, ocrFinancialColumnPages=[6])
        from tools.capital_parser import validate_summary
        self.assertTrue(validate_summary(result)['publishable'])
        result['ocrFinancialColumnPages']=[]
        self.assertFalse(validate_summary(result)['publishable'])
        # A wrong budget-column amount must fail strict source reconciliation.
        damaged=text.replace('First Nations Development Funding 682,399 - 2,289,544',
                             'First Nations Development Funding 682,399 682,399 2,289,544')
        self.assertFalse(parse_page_texts(['']*5+[damaged], fiscal_year='2024-2025', require_reported_totals=True)['publishable'])
        missing_totals=text.replace('81,616,885 111,781,540 111,249,239','').replace('75,382,755 72,291,197 65,604,895','')
        self.assertFalse(parse_page_texts(['']*5+[missing_totals], fiscal_year='2024-2025', require_reported_totals=True)['publishable'])

    def test_financial_alignment_requires_a_corresponding_year_header(self):
        items=json.loads((Path(__file__).parent/'fixtures'/'ab_467_2025_ocr_boxes.json').read_text(encoding='utf8'))
        items=[(box,text) for box,text,confidence in items if text not in ('2025','2024')]
        self.assertEqual(coordinate_lines(items, align_financial_columns=True),coordinate_lines(items))

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
