import unittest
from pathlib import Path
import json
from tools.ingest_alberta import reviewed_remuneration
from tools.parser_quality import validate_people
from run_scraper import _parse_keyword_table_row, _assign_text_money_values
from scraper import reuse_filing_result
from tools.audit_reparse import recoverable


class AuditRecoveryTests(unittest.TestCase):
    def test_nightly_reuse_retains_review_and_exact_source(self):
        prior={'href':'https://example.org/reviewed.pdf','people':[{'name':'Example Chief'}],
               'sourceTotal':100,'sha256':'reviewed-digest','manualSourceReview':{'completeSchedule':True},
               'retrievedAt':'2026-10-09','sourceVerificationStatus':'visually_verified'}
        candidate={'href':'https://example.org/new-candidate.pdf'}
        reuse_filing_result(candidate,prior)
        for key in prior:
            self.assertEqual(candidate[key],prior[key])
        candidate['people'][0]['name']='Changed'
        self.assertEqual(prior['people'][0]['name'],'Example Chief')

    def test_legacy_not_required_statement_is_still_recoverable(self):
        filing={'posted':True,'href':'https://example.org/source.pdf',
                'docType':'Audited consolidated financial statements','parse_status':'not_required'}
        self.assertTrue(recoverable(filing))
        self.assertFalse(recoverable(filing,{'publishable':True,'parseStatus':'parsed'}))

    def test_two_travel_columns_are_added_instead_of_overwritten(self):
        row = _parse_keyword_table_row(['Rodger Redman','Chief','12','60,950','60,481','1,792'],
            {0:'name',1:'role',2:'months',3:'remuneration',4:'travel',5:'travel'}, '')
        self.assertEqual(row['travel'],62273)
        self.assertEqual(row['total'],123223)

    def test_other_remuneration_is_not_travel(self):
        row = _assign_text_money_values([75000,1700,13293,89993], 'Remuneration Other Remuneration Expenses Total')
        self.assertEqual(row['otherPayments'],1700)
        self.assertEqual(row['expenses'],13293)
        self.assertIsNone(row['travel'])

    def test_fragmented_heading_cannot_validate_as_official(self):
        result = validate_people([{'name':'Title Mon','role':'Chief','remuneration':100,'total':100}],strict=True)
        self.assertTrue(result['manual_review_required'])

    def test_all_new_visual_reviews_require_exact_document(self):
        reviews = json.loads(Path('manual_overrides/audit-remuneration-reviews.json').read_text(encoding='utf-8'))['reviews']
        for review in reviews:
            band={'id':review['bandId']}; filing={'year':review['year'],'href':review['sourcePdf']}
            result=reviewed_remuneration(band,filing,review['sha256'])
            self.assertEqual(len(result['people']),review['sourceRowCount'])
            self.assertFalse(result['manual_review_required'])
            self.assertIsNone(reviewed_remuneration(band,filing,'revised-pdf'))
        standing=next(r for r in reviews if r['bandId']=='386')
        self.assertEqual(sum(p['total'] for p in standing['people']),659604)
        cote=next(r for r in reviews if r['bandId']=='366')
        self.assertEqual(sum(p['otherPayments'] for p in cote['people']),59425)

    def test_multi_scope_schedule_preserves_salary_and_honoraria(self):
        reviews = json.loads(Path('manual_overrides/audit-remuneration-reviews.json').read_text(encoding='utf-8'))['reviews']
        review = next(r for r in reviews if r['bandId']=='362' and r['year']=='2025-2026')
        self.assertIsNone(review['sourceTotal'])
        self.assertEqual(review['totalMethod'],'sum_of_reported_components')
        self.assertEqual(sum(p['remuneration'] for p in review['people']),598391)
        self.assertEqual(sum(p['reportedComponents']['entityHonorarium'] for p in review['people']),146125)
        self.assertEqual(sum(p['total'] for p in review['people']),sum(review['sourceColumnTotals'].values()))
