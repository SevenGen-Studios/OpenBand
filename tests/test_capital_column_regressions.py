import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from tools import capital_parser as parser


class CapitalColumnRegressions(unittest.TestCase):
    def test_recovery_requires_the_final_result_after_other_items(self):
        text = 'Statement of Operations\n2025 2024\nRevenue\nIndigenous Services Canada 800 700\nRental income 200 100\nTotal revenue 1,000 800\nExpenses\nEducation 500 400\nHealth 300 200\nTotal expenses 800 600\nSurplus before other items 200 200\nOther items'
        result = parser.parse_page_texts([text], fiscal_year='2024-2025', require_reported_totals=True)
        self.assertFalse(result['publishable'])
        self.assertIsNone(result['annualSurplusDeficit'])

    def test_current_year_revenue_adjustment_is_not_rental_income(self):
        self.assertNotEqual(parser.broad_revenue_category('Deferred revenue-current year'), 'Rental and property income')
        self.assertEqual(parser.broad_revenue_category('Rental income'), 'Rental and property income')

    def test_native_covid_label_and_unlabelled_totals_reconcile(self):
        text = (Path(__file__).parent / 'fixtures' / 'ab_453_2022_operations.txt').read_text(encoding='utf8')
        result = parser.parse_page_texts([text], fiscal_year='2021-2022', require_reported_totals=True)
        self.assertTrue(result['publishable'], result['warnings'])
        self.assertEqual(result['totalRevenue'], 50570203)
        self.assertEqual(result['totalExpenses'], 13496504)
        self.assertEqual(result['annualSurplusDeficit'], 34840305)
        covid = next(row for row in result['sourceExpenseRows'] if row['label'] == 'Covid-19')
        self.assertEqual(covid['amount'], 463720)
        damaged = text.replace('Covid-19 463,720 788,052', '')
        self.assertFalse(parser.parse_page_texts([damaged], fiscal_year='2021-2022', require_reported_totals=True)['publishable'])

    def test_member_savings_plan_distributions_are_reported_deductions(self):
        text = (Path(__file__).parent / 'fixtures' / 'ab_467_2023_operations.txt').read_text(encoding='utf8')
        result = parser.parse_page_texts([text], fiscal_year='2022-2023', require_reported_totals=True)
        self.assertTrue(result['publishable'], result['warnings'])
        self.assertEqual(result['totalRevenue'], 87793591)
        self.assertEqual(result['totalExpenses'], 56882299)
        self.assertEqual(result['annualSurplusDeficit'], 18087289)
        savings = next(row for row in result['surplusAdjustments'] if 'savings plan' in row['label'])
        self.assertEqual(savings['amount'], -875000)

    def test_reported_deficit_of_revenues_over_expenses(self):
        text = '''Statement of Operations
Year ended March 31, 2025
Budget 2025 2024
Revenue
Government grants 80,000 90,000 70,000
Rental income 10,000 10,000 10,000
Total revenue 90,000 100,000 80,000
Expenses
Education 50,000 70,000 55,000
Health 40,000 42,000 30,000
Total expenses 90,000 112,000 85,000
Deficit of revenues over expenses 5,000 (12,000) (5,000)'''
        result = parser.parse_page_texts([text], fiscal_year='2024-2025')
        self.assertTrue(result['publishable'], result['warnings'])
        self.assertEqual(result['annualSurplusDeficit'], -12000)

    def test_reviewed_position_field_requires_the_same_pdf_and_year(self):
        review = {'value': 53436809, 'sourceSha256': 'verified-pdf',
                  'sourceReference': {'fiscalYear': '2018-2019', 'pdfPage': 6}}
        for digest, expected in [('verified-pdf', 53436809), ('revised-pdf', None)]:
            capital = {'bands': {'462': {'years': {'2018-2019': {'fieldReviews': {'accumulatedSurplus': review}}}}}}
            summary = {'sha256': digest, 'accumulatedSurplus': None}
            parser.save_summary(capital, {'id': '462', 'name': 'Saddle Lake'}, {'year': '2018-2019'}, summary)
            self.assertEqual(summary['accumulatedSurplus'], expected)

    def test_reviewed_headline_fields_require_same_pdf_and_fiscal_year(self):
        for field in ('totalRevenue','totalExpenses','annualSurplusDeficit'):
            review={'value':100,'sourceSha256':'checked-source','sourceReference':{'fiscalYear':'2024-2025','pdfPage':7}}
            for digest,year,expected in [('checked-source','2024-2025',100),('changed-source','2024-2025',None),('checked-source','2023-2024',None)]:
                capital={'bands':{'409':{'years':{year:{'fieldReviews':{field:review}}}}}}
                summary={'sha256':digest,field:None}
                parser.save_summary(capital,{'id':'409','name':'Example'},{'year':year},summary)
                self.assertEqual(summary[field],expected)

    def test_piikani_undernoted_gain_reconciles_final_surplus(self):
        text = (Path(__file__).parent / 'fixtures' / 'ab_436_2021_operations.txt').read_text(encoding='utf8')
        result = parser.parse_page_texts([text], fiscal_year='2020-2021')
        self.assertTrue(result['publishable'], result['warnings'])
        self.assertEqual(result['totalRevenue'], 56326873)
        self.assertEqual(result['totalExpenses'], 52780568)
        self.assertEqual(result['annualSurplusDeficit'], 3581515)
        self.assertEqual(result['surplusAdjustments'][0]['amount'], 35210)
        self.assertEqual(result['totalRevenue'] - result['totalExpenses'] + parser.sum_rows(result['surplusAdjustments']), result['annualSurplusDeficit'])

    def test_preextracted_text_keeps_notes_without_rebuilding_their_tables(self):
        operations = 'Statement of Operations\n2025 2024\nRevenue\nGovernment grants 100 90\nExpenses'
        notes = 'Notes to Financial Statements\nDetails retained from native extraction'
        pdf = MagicMock()
        pdf.pages = [object(), object()]
        def extract(page, text, kind):
            if page is pdf.pages[1]:
                raise RuntimeError('Unrelated notes must not delay statement reconstruction')
            return [{'rows': [['Government grants', '100', '90']]}]
        with patch.object(parser.layout_tables, 'extract_tables_for_page', side_effect=extract):
            pages = parser.table_page_texts(pdf, [operations, notes])
        self.assertEqual(pages[1], notes)
        self.assertIn('Government grants 100 90', pages[0])

    def test_colon_section_headings_and_continued_operations_reconcile(self):
        pages = ['''Example First Nation
Statement of Operations
Year ended March 31, 2025, with comparative information for 2024
Budget 2025 2024
Revenue:
Government grants 80,000 90,000 70,000
Rental income 10,000 10,000 10,000
Total revenue 90,000 100,000 80,000
Expenses:
Education 40,000 50,000 40,000''', '''Example First Nation
Statement of Operations (continued)
Year ended March 31, 2025, with comparative information for 2024
Budget 2025 2024
Health 20,000 30,000 20,000
Total expenses 60,000 80,000 60,000
Annual surplus 30,000 20,000 20,000''']
        result = parser.parse_page_texts(pages, fiscal_year='2024-2025')
        self.assertTrue(result['publishable'], result['warnings'])
        self.assertEqual(result['totalRevenue'], 100000)
        self.assertEqual(result['totalExpenses'], 80000)
        self.assertEqual(result['annualSurplusDeficit'], 20000)
        health = next(row for row in result['sourceExpenseRows'] if row['label'] == 'Health')
        self.assertEqual(health['sourceReference']['pdfPage'], 2)

    def test_comparative_year_in_report_date_is_not_a_column(self):
        header = ('Consolidated Statement of Operations\n'
                  'Year ended March 31, 2021, with comparative information for 2020\n'
                  'Budget 2021 2020')
        column = parser.current_year_column(header, '2020-2021')
        self.assertEqual(column['selectedYear'], '2021')
        self.assertTrue(column['validated'])
        self.assertEqual(parser.actual_value([100, 120, 90], header), 120)

    def test_report_date_cannot_hide_a_wrong_actual_year(self):
        header = ('Statement of Operations\nYear ended March 31, 2025\n'
                  '2025 Budget 2024 Actual 2023 Actual')
        column = parser.current_year_column(header, '2024-2025')
        self.assertEqual(column['selectedYear'], '2024')
        self.assertFalse(column['validated'])

    def test_actual_before_budget_year_placeholder(self):
        column = parser.current_year_column(
            'Statement of Operations\nYear ended March 31\n2022\n2022 Budget 2021', '2021-2022')
        self.assertEqual(column['selectedYear'], '2022')
        self.assertTrue(column['validated'])

    def test_explicit_dashes_preserve_current_year_position(self):
        first = "Statement of Operations\n2021 Budget 2020"
        self.assertEqual(parser.actual_value([180000], first, "Trust fund transfers - - 180,000"), 0)
        second = "Statement of Operations\n2020 2020 2019\nBudget Actual Actual"
        self.assertEqual(parser.actual_value([-1092181, 1973243], second,
                                            "Funds 16 - (1,092,181) 1,973,243"), -1092181)

    def test_cold_lake_unlabelled_actual_before_budget(self):
        header = "Consolidated Statement of Operations\nYear ended March 31\n2022\n2022 Budget 2021"
        self.assertEqual(parser.actual_column_index(header), 0)
        self.assertEqual(parser.actual_value([43442193, 21668115, 34511867], header), 43442193)

    def test_cold_lake_actual_before_budget(self):
        header = "Statement of Operations\n2025 Actual 2025 Budget 2024 Actual"
        self.assertEqual(parser.actual_value([45328903, 41719304, 46987164], header), 45328903)

    def test_montana_budget_before_actual(self):
        header = "Statement of Financial Activities\n2025 Budget 2025 Actual 2024 Actual"
        self.assertEqual(parser.actual_value([16394495, 16371157, 18173882], header), 16371157)

    def test_fort_mckay_other_items_reduce_surplus(self):
        text = """Statement of Operations
2025 Budget 2025 Actual 2024 Actual
Expenses
Education 1 2 3
Other items
Settlement Trust member distribution 1,000 18,480,000 1,000
Depreciation 1,000 7,381,814 1,000
Business profit distributions 1,000 6,320,100 1,000
Annual surplus 1,000 7,308,429 1,000
"""
        rows = parser.parse_surplus_adjustments([text])
        self.assertEqual(parser.sum_rows(rows), -32181914)

    def test_revenue_other_income_is_not_surplus_adjustment(self):
        text = "Revenues\nOther income\nRental income 100 90\nExpenses\nEducation 80 70"
        self.assertEqual(parser.parse_surplus_adjustments([text]), [])

    def test_new_extraction_missing_surplus_is_blocked(self):
        summary = {
            "requiresSurplusValidation": True,
            "totalRevenue": 100, "totalExpenses": 80,
            "revenueBreakdown": [{"amount": 50}, {"amount": 50}],
            "expenseBreakdown": [{"amount": 40}, {"amount": 40}],
        }
        result = parser.validate_summary(summary)
        self.assertFalse(result["publishable"])
