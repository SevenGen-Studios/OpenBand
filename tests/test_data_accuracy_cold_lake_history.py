import copy,hashlib,json,unittest
from pathlib import Path
from tools.apply_manual_overrides import apply_record,iter_override_records
from tools.sanitize_data import sanitize_data
ROOT=Path(__file__).resolve().parents[1]
E=ROOT/'research/data-quality/2026-10-11-cold-lake-history'
TOTALS={'2019-2020':1262486,'2020-2021':1239426,'2021-2022':1317801,'2022-2023':1330635,'2023-2024':1383738,'2024-2025':1818753}
class ColdLakeHistoricalTests(unittest.TestCase):
 def filings(self,data):
  return {f['year']:f for b in data['bands'] if b['name']=='Cold Lake First Nations' for f in b['filings'] if f['year'] in TOTALS and 'Remuneration' in f['docType']}
 def test_components_both_sections_and_role_periods(self):
  fs=self.filings(json.loads((ROOT/'data.json').read_text()))
  for year,f in fs.items():
   self.assertEqual(sum(r['total'] for r in f['people']),TOTALS[year]);self.assertEqual(len(f['people']),len(set(r['name'] for r in f['people'])))
   self.assertEqual(f['sha256'],hashlib.sha256((E/(year+'.pdf')).read_bytes()).hexdigest())
   for r in f['people']:
    ps=r['sourcePaymentBreakdown'];self.assertEqual(r['total'],sum(sum(v.values()) for v in ps.values()))
    self.assertEqual(r['remuneration'],sum(v['remunerationOwnSourceRevenue'] for v in ps.values()))
    self.assertEqual(r['expenses'],sum(v['expensesOwnSourceRevenue'] for v in ps.values()))
    self.assertEqual(r['otherPayments'],0)
    if 'rolePeriods' in r:self.assertEqual(sum(p['months'] for p in r['rolePeriods']),r['months'])
  self.assertEqual(next(r for r in fs['2022-2023']['people'] if r['name']=='Kelsey Jacko')['rolePeriods'],[{'role':'Chief','months':9},{'role':'Councillor','months':3}])
 def test_override_replay_and_sanitizer(self):
  data=json.loads((ROOT/'data.json').read_text());before=copy.deepcopy(self.filings(data))
  for path in sorted((ROOT/'manual_overrides').glob('*.json')):
   for record in iter_override_records(path):apply_record(data,record)
  sanitize_data(data);self.assertEqual(before,self.filings(data))
 def test_recovery_checkpoint(self):
  for file,sha in json.loads((E/'manifest.json').read_text()).items():self.assertEqual(hashlib.sha256((E/file).read_bytes()).hexdigest(),sha)
