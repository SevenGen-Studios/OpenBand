import copy
import unittest
from tools.capital_classification import classify
from tools.capital_parser import parse_section_rows, EXPENSE_SECTION_RE, EXPENSE_SECTION_END_RE, broad_expense_category
from tools.repair_expense_categories import audit

class ExpenseRepairTests(unittest.TestCase):
    def test_programs_and_ambiguous_names(self):
        for label, category in [('Admin Services Segment','Administration'), ('Nation administration','Administration'), ('Nation Businesses Segment','Economic development'), ('Business Development Segment','Economic development')]:
            self.assertEqual(classify(label,'expense')['category'],category)
        for label in ['Investment in Business Enterprises','Nation Projects Segment','Other Programs Segment','Treaty Protectorate Segment']:
            self.assertTrue(classify(label,'expense')['reviewRequired'])

    def test_wrapped_segment_preserves_actual_column(self):
        text = 'Statement of Operations\n2025 2025 2024\nBudget Actual Actual\nExpenses\nCommunity Capital Planning and Residential Development\nSegment 7 15,256,511 19,316,478 21,735,085\nTotal expenses 15,256,511 19,316,478 21,735,085\nSurplus 0 0 0'
        rows = parse_section_rows([text],EXPENSE_SECTION_RE,EXPENSE_SECTION_END_RE,broad_expense_category,section='expenses',fiscal_year='2024-2025')
        self.assertEqual(rows[0]['sourceLabel'],'Community Capital Planning and Residential Development Segment')
        self.assertEqual(rows[0]['amount'],19316478)
        self.assertEqual(rows[0]['category'],'Infrastructure / public works')

    def test_preservation_details_and_idempotence(self):
        s=dict(parseStatus='parsed',totalExpenses=150,sourceExpenseRows=[dict(label='Governance',category='Operations',amount=100),dict(label='Other programs',category='Operations',amount=50)],expenseBreakdown=[dict(category='Operations',amount=150)],expenseDetails=[dict(sourceLabel='Governance',label='Salaries',category='Operations',amount=100)])
        d={'bands':{'1':{'years':{'2024-2025':s}}}};before=copy.deepcopy(d)
        fixed,report=audit(d,{})
        self.assertEqual(d,before)
        self.assertEqual(len(report['corrections']),1)
        self.assertEqual(len(report['reviewQueue']),1)
        self.assertEqual(fixed['bands']['1']['years']['2024-2025']['expenseDetails'][0]['category'],'Administration')
        again,report=audit(fixed,{})
        self.assertEqual(again,fixed);self.assertEqual(report['corrections'],[])
        s['sourceExpenseRows'][0]['manualVerified']=True
        fixed,report=audit(d,{})
        self.assertEqual(report['corrections'],[])
