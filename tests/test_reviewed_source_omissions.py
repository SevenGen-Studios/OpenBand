import copy
import json
from pathlib import Path
import unittest
from tools.parser_quality import validate_people
from tools.apply_manual_overrides import apply_record
ROOT=Path(__file__).resolve().parents[1]
class ReviewedOmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reviews=json.loads((ROOT/'research/remuneration-recovery/2026-11-28/second-pass/verified-reviews.json').read_text())['reviews']
    def review(self,bid,year):return next(r for r in self.reviews if r['bandId']==bid and r['year']==year)
    def test_names_are_omitted_not_invented(self):
        r=self.review(467,'2024-2025');self.assertEqual(len(r['people']),5)
        self.assertTrue(all(p['name'] is None for p in r['people']))
        self.assertTrue(validate_people(r['people'],strict=True)['manual_review_required'])
        self.assertFalse(validate_people(r['people'],strict=True,source_review=r)['manual_review_required'])
        self.assertEqual(sum(p['total'] for p in r['people']),2216803)
    def test_roles_are_omitted_not_defaulted_to_councillor(self):
        for year in ['2023-2024','2024-2025']:
            r=self.review(455,year);self.assertTrue(all(p['role']=='Not specified' for p in r['people']))
            self.assertTrue(validate_people(r['people'],strict=True)['manual_review_required'])
            self.assertFalse(validate_people(r['people'],strict=True,source_review=r)['manual_review_required'])
    def test_dashes_do_not_become_zero_or_delete_the_official(self):
        r=self.review(288,'2023-2024');v=validate_people(r['people'],source_total=172604,strict=True,source_review=r)
        self.assertFalse(v['manual_review_required']);self.assertEqual(len(v['people']),7)
        row=next(p for p in v['people'] if p['name']=='Deborah Houle')
        for key in ['remuneration','travel','otherPayments','total']:self.assertIsNone(row[key])
    def test_unbound_or_incomplete_review_cannot_authorize_omissions(self):
        r=copy.deepcopy(self.review(288,'2023-2024'))
        for field,value in [('sha256','b'*64),('completeSchedule',False),('sourceRowCount',6)]:
            broken={**r,field:value};self.assertTrue(validate_people(r['people'],strict=True,source_review=broken)['manual_review_required'])
    def test_source_row_numbers_cannot_be_duplicated(self):
        r=copy.deepcopy(self.review(467,'2024-2025'));r['people'][1]['sourceRowNumber']=1
        self.assertTrue(validate_people(r['people'],strict=True,source_review=r)['manual_review_required'])
    def test_original_baseline_is_archived_and_only_data_fingerprint_changes(self):
        old=json.loads((ROOT/'research/remuneration-recovery/2026-11-28/second-pass/prior-protected-baseline.json').read_text());new=json.loads((ROOT/'tools/manitoba-source-cache/protected-baseline.json').read_text())
        self.assertNotEqual(old['files']['data.json'],new['files']['data.json']);old['files'].pop('data.json');new['files'].pop('data.json');self.assertEqual(old,new)
    def test_exchanged_isc_labels_are_replayed_before_rows(self):
        data=json.loads((ROOT/'data.json').read_text())
        rec=next(r for r in json.loads((ROOT/'manual_overrides/recovered_2026_11_28_second_pass.json').read_text())['overrides'] if r['band'].startswith("Beardy"))
        band=next(b for b in data['bands'] if b['id']==369)
        for f in band['filings']:
            if f['year']=='2024-2025':
                f['docType']=f['listedDocType'];f['people']=[];f.pop('manualSourceReview',None)
        apply_record(data,rec)
        remuneration=next(f for f in band['filings'] if f['year']=='2024-2025' and 'remuneration' in f['docType'].lower())
        self.assertIn('DOC=Audited',remuneration['href']);self.assertEqual(len(remuneration['people']),7)

    def test_override_replay_preserves_unknown_fields(self):
        data=json.loads((ROOT/'data.json').read_text());rec=next(r for r in json.loads((ROOT/'manual_overrides/recovered_2026_11_28_second_pass.json').read_text())['overrides'] if r['band']=='Dakota Plains');b=next(b for b in data['bands'] if b['id']==288);f=next(f for f in b['filings'] if f['year']=='2023-2024' and 'remuneration' in f['docType'].lower());f.pop('manualSourceReview');f['people']=[];apply_record(data,rec);self.assertEqual(len(f['people']),7);self.assertIsNone(f['people'][5]['total'])
if __name__=='__main__':unittest.main()
