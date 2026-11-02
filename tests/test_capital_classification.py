import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.capital_classification import classify
from tools.capital_parser import aggregate_categories, broad_revenue_category, validate_summary
from tools.audit_capital_data import safely_rebuild_breakdown
from tools.audit_capital_classification import audit_dataset, apply_verified, valid_evidence
from tools.capital_detail_enricher import select_safe_details
from tools.merge_capital_recovery import merge_recovery


class ClassificationTests(unittest.TestCase):
    def test_government_is_not_a_donation(self):
        for label in ['Government contributions', 'Health Canada', 'Indigenous and Northern Affairs Canada',
                      'First Nation and Inuit Health Branch', 'Employment and Social Development Canada']:
            self.assertEqual(classify(label, 'revenue')['category'], 'Government funding and transfers', label)
        self.assertEqual(classify('Donations', 'revenue')['category'], 'Donations or contributions')
        for label in ['Contributions', 'Grant funding', 'Tribal council', 'Industry contributions']:
            d = classify(label, 'revenue')
            self.assertEqual(d['category'], 'Unclassified')
            self.assertTrue(d['reviewRequired'])

    def test_business_ownership_is_not_government_funding(self):
        for label in ['Income from government business enterprises - other',
                      'Loss in Government Business Enterprises', 'Gain from investment in Nation business entities']:
            self.assertEqual(broad_revenue_category(label), 'Business and enterprise revenue')
        self.assertEqual(classify('Trust', 'revenue', parent_label='Income from government business enterprises - NOHA')['category'],
                         'Business and enterprise revenue')

    def test_trust_requires_accounting_context(self):
        for label in ['First Nations Trust', 'Land Claim Settlement Trust', 'Trust distribution', 'Loan proceeds']:
            self.assertEqual(classify(label, 'revenue')['category'], 'Unclassified')
            self.assertTrue(classify(label, 'revenue')['reviewRequired'])
        self.assertEqual(classify('Trust investment income', 'revenue')['category'], 'Investment income')
        self.assertEqual(classify('Settlement proceeds', 'revenue')['category'], 'Settlement and claim revenue')
        self.assertEqual(classify('Land Claims', 'expense')['category'], 'Land Claims')
        self.assertTrue(classify('Transfer to settlement trust', 'expense')['reviewRequired'])

    def test_assets_are_not_operating_programs(self):
        self.assertTrue(classify('Tangible capital assets', 'expense')['reviewRequired'])
        self.assertEqual(classify('Infrastructure operations and maintenance', 'expense')['category'], 'Infrastructure / public works')
        self.assertTrue(classify('Gain on asset sales', 'revenue')['reviewRequired'])
        self.assertEqual(classify('Gain on asset sales', 'revenue')['category'], 'Other revenue')

    def test_program_administration_and_unknown_labels_require_review(self):
        self.assertTrue(classify('Program administration', 'expense')['reviewRequired'])
        self.assertEqual(classify('Administration', 'expense', parent_label='Education')['category'], 'Education')
        self.assertEqual(classify('Housing administration', 'expense')['category'], 'Housing')
        self.assertEqual(classify('Governance', 'expense')['category'], 'Administration')
        for label in ['Unknown acronym', 'Reserves and Trusts', 'Makoose C Gamick', 'Other programs']:
            self.assertTrue(classify(label, 'expense')['reviewRequired'])
        self.assertFalse(classify('Amortization', 'expense')['reviewRequired'])

    def test_deferred_revenue_and_subtotals_do_not_receive_funding_guesses(self):
        for label in ['Deferred government contributions', 'Contributions carried forward from prior year',
                      'Revenue (Continued from previous page)', 'Eliminations', 'Internal transfer']:
            self.assertTrue(classify(label, 'revenue')['reviewRequired'])
            self.assertEqual(classify(label, 'revenue')['category'], 'Unclassified')

    def test_reviewed_row_and_summary_are_not_overwritten(self):
        row = dict(sourceLabel='Trust', category='Business and enterprise revenue', amount=100,
                   classificationReview={'status': 'verified_correct', 'evidenceId': 'review-1'},
                   fullSourceLabel='Income from government business enterprises - NOHA Trust',
                   sourceReference={'section': 'revenue'})
        d = classify('Trust', 'revenue', row=row)
        self.assertEqual(d['category'], row['category'])
        breakdown, sources = aggregate_categories([row])
        self.assertEqual(sources[0]['classificationReview'], row['classificationReview'])
        self.assertEqual(sources[0]['fullSourceLabel'], row['fullSourceLabel'])
        for flag in ['verified', 'manualVerified', 'manual_override']:
            summary = {flag: True, 'totalRevenue': 100, 'sourceRevenueRows': [row], 'revenueBreakdown': breakdown}
            before = copy.deepcopy(summary)
            self.assertFalse(safely_rebuild_breakdown(summary, 'sourceRevenueRows', 'totalRevenue', broad_revenue_category))
            self.assertEqual(summary, before)

    def test_unreadable_source_row_does_not_disappear_in_rebuild(self):
        s = dict(totalRevenue=100, sourceRevenueRows=[{'label':'Store sales','amount':100}, {'label':'bad','amount':'unreadable'}])
        before = copy.deepcopy(s)
        self.assertFalse(safely_rebuild_breakdown(s, 'sourceRevenueRows', 'totalRevenue', broad_revenue_category))
        self.assertEqual(s, before)

    def test_enrichment_preserves_parent_category_and_rejects_duplicates(self):
        existing = {'sourceExpenseRows':[dict(label='Makoose', amount=100, category='Social programs')]}
        parsed = dict(expenseDetailSchedules=[dict(sourceLabel='Makoose', reportedTotal=100, reconciles=True, category='Operations')],
                      expenseDetails=[dict(sourceLabel='Makoose', label='Salaries', amount=100, category='Operations')])
        details, schedules = select_safe_details(existing, parsed)
        self.assertEqual(details[0]['category'], 'Social programs')
        self.assertEqual(schedules[0]['category'], 'Social programs')
        existing['sourceExpenseRows'] *= 2
        self.assertEqual(select_safe_details(existing, parsed), ([], []))


class EvidenceGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        pdf = self.root / 'original.pdf'; pdf.write_bytes(b'%PDF-test-evidence')
        self.data = {'bands':{'1':{'name':'Test Nation','years':{'2024-2025':{
            'sourceUrl':'https://example.com/original.pdf', 'fiscalYear':'2024-2025',
            'parseStatus':'parsed', 'publishable':True, 'totalRevenue':100, 'totalExpenses':80,
            'annualSurplusDeficit':20,
            'sourceRevenueRows':[dict(label='Health Canada', category='Unclassified', amount=100,
                                     sourceReference=dict(section='revenue', selectedYear='2025'))],
            'sourceExpenseRows':[dict(label='Health', category='Health', amount=80)],
            'revenueBreakdown':[dict(category='Unclassified', amount=100)],
            'expenseBreakdown':[dict(category='Health', amount=80)]}}}}}
        self.inventory = {'bands':[dict(id=1, province='SK')]}
        self.ev = dict(bandId='1', fiscalYear='2024-2025', kind='revenue', rowIndex=0,
            sourceLabel='Health Canada', originalCategory='Unclassified', amount=100,
            sourceUrl='https://example.com/original.pdf', pdfPath='original.pdf',
            pdfSha256=hashlib.sha256(pdf.read_bytes()).hexdigest(), pdfPage=8,
            status='verified_misclassification', proposedCategory='Government funding and transfers',
            reviewer='test', verificationMethod='independent_pdf_review',
            checks={k:True for k in ['nation','fiscalYear','section','actualColumn','amount','notDuplicated','accountingContext']},
            explanation='Direct government contribution verified', excerpt='Health Canada 100')

    def audit(self, evidence=True):
        return audit_dataset(self.data, self.inventory, {'rows':[self.ev]} if evidence else {}, self.root)

    def test_read_only_check_cannot_create_verified_evidence(self):
        before = copy.deepcopy(self.data)
        report = self.audit(False)
        self.assertEqual(self.data, before)
        self.assertEqual(report['counts']['statuses'], {'ambiguous':2})
        self.assertEqual(report['counts']['independentlyPdfReviewedRows'], 0)
        after, trail = apply_verified(self.data, report)
        self.assertEqual(after, before)
        self.assertEqual(trail['changes'], [])

    def test_evidence_gated_apply_preserves_every_financial_value_and_undo(self):
        before = copy.deepcopy(self.data)
        report = self.audit()
        after, undo = apply_verified(self.data, report)
        self.assertEqual(self.data, before)
        old = before['bands']['1']['years']['2024-2025']
        new = after['bands']['1']['years']['2024-2025']
        self.assertEqual(new['totalRevenue'], old['totalRevenue'])
        self.assertEqual(new['sourceRevenueRows'][0]['amount'], 100)
        self.assertEqual(sum(r['amount'] for r in new['revenueBreakdown']), 100)
        self.assertEqual(undo['beforeSummaries']['1:2024-2025'], old)
        self.assertEqual(new['sourceRevenueRows'][0]['category'], 'Government funding and transfers')

    def test_hash_or_row_lease_failure_prevents_apply(self):
        for field, value in [('pdfSha256','bad'), ('amount',101), ('originalCategory','Other revenue'), ('sourceUrl','wrong')]:
            with self.subTest(field=field):
                original = self.ev[field]; self.ev[field] = value
                report = self.audit()
                self.assertTrue(report['evidenceErrors'])
                with self.assertRaises(ValueError):apply_verified(self.data, report)
                self.ev[field] = original

    def test_wrong_year_or_section_cannot_be_overridden_by_manifest(self):
        row = self.data['bands']['1']['years']['2024-2025']['sourceRevenueRows'][0]
        row['sourceReference']['section'] = 'liabilities'
        report = self.audit()
        self.assertEqual(report['rows'][0]['status'], 'extraction_issue')
        self.assertEqual(apply_verified(self.data, report)[1]['changes'], [])

    def test_partial_review_does_not_become_full_verification(self):
        self.ev['checks']['accountingContext'] = False
        self.assertTrue(self.audit()['evidenceErrors'])
        self.assertFalse(self.audit()['completeIndependentPdfVerification'])

    def test_exact_reconciliation_flags_small_difference(self):
        s = self.data['bands']['1']['years']['2024-2025']
        s['totalRevenue'] = 101
        report = self.audit(False)
        self.assertEqual(report['counts']['reconciliationFailures'], 1)
        self.assertEqual(report['summaries'][0]['reconciliation']['revenue']['differences']['sourceDifference'], -1)

    def test_missing_source_breakdown_is_a_coverage_gap(self):
        del self.data['bands']['1']['years']['2024-2025']['sourceRevenueRows']
        report = self.audit(False)
        self.assertEqual(report['counts']['missingSourceCategoryRows'], 1)
        self.assertEqual(report['rows'][0]['status'], 'extraction_issue')

    def test_reviewed_summary_requires_explicit_source_supersession(self):
        self.data['bands']['1']['years']['2024-2025']['manual_override'] = True
        with self.assertRaises(ValueError):apply_verified(self.data, self.audit())
        self.ev['supersedesReviewedDecision'] = True
        self.assertEqual(len(apply_verified(self.data, self.audit())[1]['changes']), 1)

class WrappedBusinessLabelTests(unittest.TestCase):
    def test_wrapped_statement_label_keeps_business_context(self):
        from tools.capital_parser import parse_page_texts
        page = '''Example First Nation
Consolidated Statement of Operations
For the year ended March 31, 2023
2023 2023 2022
Budget Actual Actual
Revenue
Indigenous Services Canada - 500 400
Income from government business enterprises - NOHA
Trust - 300 200
Total revenue - 800 600
Expenses
Health - 400 300
Education - 200 200
Total expenses - 600 500
Annual surplus - 200 100
'''
        result = parse_page_texts([page], fiscal_year='2022-2023')
        row = next(r for r in result['sourceRevenueRows'] if 'NOHA' in r['label'])
        self.assertEqual(row['category'], 'Business and enterprise revenue')
        self.assertEqual(row['amount'], 300)
        self.assertIn('Trust', row['label'])
        self.assertEqual(row['sourceReference']['selectedYear'], '2023')


if __name__ == '__main__':
    unittest.main()
