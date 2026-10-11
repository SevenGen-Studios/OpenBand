import copy,hashlib,json,unittest
from pathlib import Path
from tools.apply_manual_overrides import apply_record,iter_override_records
from tools.sanitize_data import sanitize_data
ROOT=Path(__file__).resolve().parents[1]
EVIDENCE=ROOT/'research/data-quality/2026-10-11-cold-lake'
class ColdLakeSourceTests(unittest.TestCase):
 def filing(self,data):
  return next(f for b in data['bands'] if b['name']=='Cold Lake First Nations' for f in b['filings'] if f['year']=='2025-2026' and 'Remuneration' in f['docType'])
 def test_full_schedule_and_components(self):
  f=self.filing(json.loads((ROOT/'data.json').read_text()));rows=f['people']
  self.assertEqual(len(rows),10)
  self.assertEqual([sum(r[k] for r in rows) for k in ['remuneration','travel','expenses','otherPayments','total']],[1462188,198500,137563,38345,1836596])
  self.assertEqual(rows[0]['total'],294374)
  for r in rows:
   parts=r['sourcePaymentBreakdown'];self.assertEqual(r['total'],sum(sum(p.values()) for p in parts.values()))
   self.assertEqual(r['remuneration'],sum(p['honoraria'] for p in parts.values()))
   self.assertEqual(r['otherPayments'],sum(p['pensionContribution'] for p in parts.values()))
  self.assertEqual(f['sha256'],hashlib.sha256((EVIDENCE/'source.pdf').read_bytes()).hexdigest())
 def test_replay_and_sanitizer_protect_review(self):
  data=json.loads((ROOT/'data.json').read_text());expected=copy.deepcopy(self.filing(data))
  for path in sorted((ROOT/'manual_overrides').glob('*.json')):
   for record in iter_override_records(path):apply_record(data,record)
  sanitize_data(data);self.assertEqual(self.filing(data),expected)
 def test_recovery_manifest(self):
  for path,sha in json.loads((EVIDENCE/'manifest.json').read_text()).items():
   self.assertEqual(hashlib.sha256((EVIDENCE/path).read_bytes()).hexdigest(),sha)
