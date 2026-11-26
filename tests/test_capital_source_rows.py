"""One Arrow 2023-2024 source-row restoration and publication integrity."""
import copy
import hashlib
import json
import unittest
from pathlib import Path
from tools.capital_parser import validate_summary
from tools.audit_capital_classification import reconciliation, audit_dataset

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT/'research/classification-audit/2026-11-25/one-arrow-2024'

class SourceRowsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.summary=json.loads((ROOT/'capital-data.json').read_text())['bands']['373']['years']['2023-2024']
        cls.evidence=json.loads((EVIDENCE/'evidence.json').read_text())

    def test_source_and_categories_reconcile_without_changing_reported_totals(self):
        for kind in ['revenue','expense']:
            self.assertEqual(reconciliation(self.summary,kind)['differences'],{})
        for field in ['totalRevenue','totalExpenses','annualSurplusDeficit','capitalSpending','capitalAssets','debt','cashInvestments','sourceUrl']:
            self.assertEqual(self.summary[field],self.evidence['beforeSummary'][field])
        self.assertEqual(len(self.summary['sourceRevenueRows']),13)
        self.assertEqual(len(self.summary['sourceExpenseRows']),10)
        self.assertTrue(validate_summary(self.summary)['publishable'])

    def test_original_source_amounts_and_current_year_are_bound_to_pdf(self):
        self.assertEqual(hashlib.sha256((EVIDENCE/'source.pdf').read_bytes()).hexdigest(),self.evidence['pdfSha256'])
        for row in self.summary['sourceRevenueRows']+self.summary['sourceExpenseRows']:
            self.assertEqual(row['sourceReference']['pdfPage'],8)
            self.assertEqual(row['sourceReference']['selectedYear'],'2024')
            self.assertEqual(row['classificationReview']['pdfSha256'],self.evidence['pdfSha256'])
        import pdfplumber
        with pdfplumber.open(EVIDENCE/'source.pdf') as pdf:
            words=pdf.pages[7].extract_words()
        headers={word['text']:(word['x0']+word['x1'])/2 for word in words
                 if word['text'] in ['Budget','2024','2023']}
        left=(headers['Budget']+headers['2024'])/2
        right=(headers['2024']+headers['2023'])/2
        actual_cells={word['text'] for word in words if left < (word['x0']+word['x1'])/2 < right}
        for amount in [r['amount'] for r in self.evidence['rows']]:
            self.assertIn(f'{amount:,}',actual_cells)

    def test_unresolved_funders_do_not_become_government_by_residual(self):
        rows=self.summary['sourceRevenueRows']
        unknown=[r for r in rows if r['category']=='Unclassified']
        self.assertEqual(sum(r['amount'] for r in unknown),6656062)
        self.assertEqual(len(unknown),3)
        self.assertTrue(all(r['classificationReview']['reviewRequired'] for r in unknown))
        govt=next(r for r in self.summary['revenueBreakdown'] if r['category']=='Government funding and transfers')
        self.assertEqual(govt['amount'],22587916)
        self.assertEqual(sum(r['categoryVerified'] for r in self.evidence['rows']),20)

    def test_review_manifest_passes_independent_evidence_gate(self):
        report=audit_dataset({'bands':{'373':{'name':'One Arrow First Nation',
            'years':{'2023-2024':self.summary}}}},
            {'bands':[dict(id=373,iscBandNumber=373,province='SK')]},self.evidence,ROOT)
        self.assertEqual(report['evidenceErrors'],[])
        self.assertEqual(report['unusedEvidence'],[])
        self.assertEqual(report['counts']['independentlyPdfReviewedRows'],23)
        self.assertEqual(report['counts']['statuses'],{'verified_correct':20,'ambiguous':3})

    def test_original_override_producer_preserves_restoration(self):
        override=json.loads((ROOT/'capital_overrides/one_arrow_2021_2024.json').read_text())['years']['2023-2024']
        for key in ['sourceRevenueRows','sourceExpenseRows','revenueBreakdown','sourceRowReview']:
            self.assertEqual(override[key],self.summary[key])

    def test_category_totals_cannot_hide_broken_source_activity(self):
        for key in ['sourceRevenueRows','sourceExpenseRows']:
            for failure in ['missing_row','unreadable','duplicate_total','one_dollar']:
                with self.subTest(key=key,failure=failure):
                    s=copy.deepcopy(self.summary)
                    if failure=='missing_row':s[key].pop(0)
                    elif failure=='unreadable':s[key][0]['amount']=None
                    elif failure=='one_dollar':s[key][0]['amount']-=1
                    else:s[key].append(dict(label='Total',amount=s['totalRevenue' if key=='sourceRevenueRows' else 'totalExpenses']))
                    self.assertFalse(validate_summary(s)['publishable'])
