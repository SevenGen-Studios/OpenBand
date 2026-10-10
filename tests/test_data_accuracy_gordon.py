import copy
import hashlib
import json
import unittest
from pathlib import Path

from tools.apply_manual_overrides import apply_record, iter_override_records
from tools.sanitize_data import sanitize_data

ROOT=Path(__file__).resolve().parents[1]
EVIDENCE=ROOT/'research/data-quality/2026-10-10-next'


class FurtherSourceReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=json.loads((ROOT/'data.json').read_text())
        cls.cases=json.loads((EVIDENCE/'reviewed-cases.json').read_text())['cases']

    def filing(self,data,c):
        return next(f for b in data['bands'] if str(b['id'])==c['bandId']
                    for f in b['filings'] if f['year']==c['year'] and 'remuneration' in f['docType'].lower())

    def test_column_meaning_and_missing_half_month_payment(self):
        day=next(c for c in self.cases if c['bandId']=='389')
        rows=self.filing(self.data,day)['people']
        self.assertEqual(sum(p['expenses'] for p in rows),53038)
        self.assertEqual(sum(p['otherPayments'] for p in rows),314250)
        self.assertTrue(all(p['travel'] is None for p in rows))
        gordon=next(c for c in self.cases if c['bandId']=='391' and c['year']=='2018-2019')
        rows=self.filing(self.data,gordon)['people']
        john=next(p for p in rows if p['name']=='John McNab')
        self.assertEqual((john['role'],john['months'],john['total']),('Chief',.5,5600))
        self.assertEqual(sum(p['total'] for p in rows),631926)
        for c in self.cases:
            self.assertEqual(self.filing(self.data,c),c['after'])
            if c['bandId']=='391':
                for row in c['after']['people']:
                    b=row['otherPaymentsBreakdown']
                    self.assertFalse(b['entityRemunerationExpenseSplitDisclosed'])
                    self.assertEqual(row['otherPayments'],b['otherRemuneration']+b['otherEntityRemunerationAndExpenses'])

    def test_every_override_and_sanitizer_retains_reviewed_evidence(self):
        data=copy.deepcopy(self.data)
        for path in sorted((ROOT/'manual_overrides').glob('*.json')):
            for record in iter_override_records(path):apply_record(data,record)
        sanitize_data(data)
        for c in self.cases:self.assertEqual(self.filing(data,c),c['after'])

    def test_recovery_manifest_and_remaining_queue(self):
        for e in json.loads((EVIDENCE/'manifest.json').read_text())['files']:
            self.assertEqual(hashlib.sha256((EVIDENCE/e['path']).read_bytes()).hexdigest(),e['sha256'])
        queue=json.loads((EVIDENCE/'remaining-review-queue.json').read_text())
        self.assertEqual(queue['count'],len(queue['filings']))
        self.assertEqual(queue['count'],498)


if __name__=='__main__':unittest.main()
