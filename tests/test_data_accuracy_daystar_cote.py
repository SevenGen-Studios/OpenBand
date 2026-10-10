import copy
import gzip
import hashlib
import json
import unittest
from pathlib import Path

from tools.apply_manual_overrides import apply_record, iter_override_records
from tools.sanitize_data import sanitize_data

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'research/data-quality/2026-10-10'


class DayStarCoteSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((ROOT / 'data.json').read_text())
        cls.cases = json.loads((EVIDENCE / 'reviewed-cases.json').read_text())['cases']

    def filing(self, data, case):
        return next(f for b in data['bands'] if str(b['id']) == case['bandId']
                    for f in b['filings'] if f['year'] == case['year'] and 'remuneration' in f['docType'].lower())

    def test_current_totals_and_original_evidence_are_preserved(self):
        for c in self.cases:
            with self.subTest(year=c['year'], band=c['bandId']):
                f = self.filing(self.data, c)
                self.assertEqual(f, c['after'])
                self.assertEqual(sum(r['total'] for r in f['people']), c['afterTotal'])
                self.assertEqual(sum(r['total'] for r in c['before']['people']), c['beforeTotal'])
                for r in f['people']:
                    self.assertIsNone(r['creditCard'])
                    self.assertIsNone(r['travel'])
                    self.assertEqual(r['total'], r['remuneration'] + r['expenses'] + (r['otherPayments'] or 0))
        daystar = self.filing(self.data, next(c for c in self.cases if c['bandId']=='389' and c['year']=='2014-2015'))
        linda = next(r for r in daystar['people'] if r['name']=='Linda Kinequon')
        self.assertEqual(linda['total'], 0)
        self.assertEqual(linda['comparativeDisclosure']['reportedTotal'], 32569)
        cote = self.filing(self.data, next(c for c in self.cases if c['bandId']=='366' and c['year']=='2019-2020'))
        tyrone = next(r for r in cote['people'] if r['name']=='Keshane, Tyrone')
        self.assertEqual((tyrone['otherPayments'], tyrone['expenses'], tyrone['total']), (6890,43487,86377))

    def test_replay_cannot_erase_reviewed_values(self):
        data = copy.deepcopy(self.data)
        for path in sorted((ROOT/'manual_overrides').glob('*.json')):
            for record in iter_override_records(path):
                apply_record(data, record)
        sanitize_data(data)
        for c in self.cases:
            self.assertEqual(self.filing(data,c),c['after'])

    def test_recovery_checkpoint_hashes_and_queue(self):
        manifest = json.loads((EVIDENCE/'manifest.json').read_text())
        for entry in manifest['files']:
            p = EVIDENCE/entry['path']
            self.assertEqual(p.stat().st_size,entry['bytes'])
            self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),entry['sha256'])
            if p.name.endswith('.json.gz'):
                json.loads(gzip.decompress(p.read_bytes()))
        queue = json.loads((EVIDENCE/'remaining-review-queue.json').read_text())
        self.assertEqual(queue['count'],len(queue['filings']))
        self.assertEqual(queue['count'],502)
        self.assertEqual(sum(f['status']=='confirmed_source_arithmetic_conflict' for f in queue['filings']),2)
        done = {(c['bandId'],c['year']) for c in self.cases}
        self.assertTrue(all((str(f['bandId']),f['year']) not in done for f in queue['filings']))


if __name__ == '__main__':
    unittest.main()
