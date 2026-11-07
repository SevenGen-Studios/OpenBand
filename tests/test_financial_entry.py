import json
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from tools.financial_entry import apply, components, publish, validate
from tools.sanitize_data import sanitize_filing
from tools.apply_manual_overrides import apply_record


def fixture():
    rows = [dict(name='Example Chief', role='Chief', months=12, remuneration=105000,
                 travel=200, expenses=50, creditCard=10, travelExpenses=260,
                 otherPayments=0, other=0, total=105260, extra='preserve'),
            dict(name='Example Councillor', role='Councillor', months=None,
                 remuneration=100, travel=None, expenses=None, creditCard=None,
                 travelExpenses=None, otherPayments=None, other=None, total=None)]
    filing = dict(year='2024-2025', docType='Remuneration', href='https://services.sac-isc.gc.ca/source.pdf',
                  people=rows, posted=True, parse_status='parsed', untouched='keep')
    data = {'bands':[dict(id='1',name='Example Nation',province='SK',filings=[filing])]}
    draft = dict(schema='openband-remuneration-v1', bandId='1',band='Example Nation',province='SK',
                 year='2024-2025', before=deepcopy(filing), people=deepcopy(rows), state='approved',
                 editedBy='editor', approvedBy='verifier', approvedAt='2026-11-06T12:00:00Z',revision='fixture-v1',
                 source=dict(url=filing['href'],sha256='a'*64,pages='3',identityAndYearConfirmed=True,completeSchedule=True))
    return data, draft


class FinancialEntryTests(unittest.TestCase):
    def test_single_correction_preserves_unrelated_fields(self):
        data,draft=fixture(); draft['people'][0].update(remuneration=15000,total=15260)
        apply(data,draft,True); f=data['bands'][0]['filings'][0]
        self.assertEqual(f['people'][0]['remuneration'],15000)
        self.assertEqual(f['people'][0]['expenses'],50)
        self.assertEqual(f['people'][0]['extra'],'preserve')
        self.assertEqual(f['people'][1]['remuneration'],100)
        self.assertIsNone(f['people'][1]['otherPayments'])
        self.assertEqual(f['untouched'],'keep')

    def test_adding_missing_filing_is_idempotent(self):
        data,draft=fixture(); data['bands'][0]['filings']=[]; draft['before']=None
        apply(data,draft,True);apply(data,draft)
        self.assertEqual(len(data['bands'][0]['filings']),1)

    def test_add_remove_and_several_figures(self):
        data,draft=fixture(); draft['people']=draft['people'][:1]
        draft['people'][0].update(name='Corrected Chief',remuneration=15000,total=15260)
        apply(data,draft,True);self.assertEqual(len(data['bands'][0]['filings'][0]['people']),1)

    def test_null_and_zero_survive_sanitizer(self):
        data,draft=fixture(); apply(data,draft,True); f=data['bands'][0]['filings'][0]
        before=deepcopy(f['people']);sanitize_filing(f)
        self.assertEqual(f['people'],before)
        self.assertEqual(f['people'][0]['other'],0)
        self.assertIsNone(f['people'][1]['other'])

    def test_aggregate_is_not_double_counted(self):
        _,draft=fixture();self.assertEqual(components(draft['people'][0]),[105000,260,0])

    def test_rejects_unreconciled_reported_total(self):
        _,draft=fixture();draft['people'][0]['total']=12
        with self.assertRaisesRegex(ValueError,'reconcile'):validate(draft)

    def test_schedule_total_requires_known_values(self):
        _,draft=fixture();draft['source']['scheduleTotal']=105260
        with self.assertRaisesRegex(ValueError,'reconcile'):validate(draft)

    def test_duplicate_official_rejected(self):
        _,draft=fixture();draft['people'].append(deepcopy(draft['people'][0]))
        with self.assertRaisesRegex(ValueError,'Duplicate'):validate(draft)

    def test_draft_or_self_approval_rejected(self):
        _,draft=fixture();draft['state']='draft'
        with self.assertRaises(ValueError):validate(draft)
        draft['state']='approved';draft['approvedBy']='editor'
        with self.assertRaises(ValueError):validate(draft)

    def test_math_does_not_imply_source_verification(self):
        _,draft=fixture();draft['source']['completeSchedule']=False
        with self.assertRaisesRegex(ValueError,'verification'):validate(draft)

    def test_invalid_money_rejected(self):
        for amount in [True,float('nan'),float('inf'),'100']:
            _,draft=fixture();draft['people'][0]['remuneration']=amount
            with self.assertRaises(ValueError):validate(draft)

    def test_stale_before_image_rejected(self):
        data,draft=fixture();data['bands'][0]['filings'][0]['people'][0]['name']='Concurrent edit'
        with self.assertRaisesRegex(ValueError,'changed'):apply(data,draft,True)

    def test_scraper_replay_restores_corrected_schedule(self):
        data,draft=fixture();draft['people'][0].update(remuneration=15000,total=15260)
        apply(data,draft,True)
        data['bands'][0]['filings'][0]['people']=[]
        apply_record(data,draft)
        self.assertEqual(data['bands'][0]['filings'][0]['people'][0]['remuneration'],15000)

    def test_new_source_is_not_silently_overwritten(self):
        data,draft=fixture();data['bands'][0]['filings'][0]['href']='https://example.com/revised.pdf'
        with self.assertRaisesRegex(ValueError,'Source URL changed'):apply(data,draft)

    def test_full_publish_and_duplicate_dispatch(self):
        data,draft=fixture()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'manual_overrides').mkdir();(root/'data.json').write_text(json.dumps(data))
            self.assertTrue(publish(root,draft));self.assertFalse(publish(root,draft))
            saved=json.loads((root/'manual_overrides/zz-admin-1-2024-2025.json').read_text())
            self.assertEqual(saved['before'],draft['before'])

    def test_reverse_previous_correction(self):
        data,draft=fixture();draft['people'][0].update(remuneration=15000,total=15260);apply(data,draft,True)
        undo=deepcopy(draft);undo.update(before=deepcopy(data['bands'][0]['filings'][0]),people=draft['before']['people'],revision='fixture-reversal')
        apply(data,undo,True);self.assertEqual(data['bands'][0]['filings'][0]['people'][0]['remuneration'],105000)

    def test_replay_writer_boundary_and_alberta_names(self):
        from tools.financial_entry import replay_managed
        from tools.sanitize_data import sanitize_data
        data,draft=fixture(); data['bands'][0]['province']='AB'; draft['province']='AB'
        draft['people'][0]['name']='McDonald Chief'
        with tempfile.TemporaryDirectory() as directory:
            Path(directory,'zz-admin-1-2024-2025.json').write_text(json.dumps(draft))
            replay_managed(data,directory)
            sanitize_data(data)
            self.assertEqual(data['bands'][0]['filings'][0]['people'][0]['name'],'McDonald Chief')

    def test_source_hash_changes_fail_closed(self):
        data,draft=fixture();data['bands'][0]['filings'][0]['sha256']='b'*64
        with self.assertRaisesRegex(ValueError,'hash changed'):apply(data,draft)

    def test_public_assets_are_unchanged(self):
        import hashlib
        root=Path(__file__).resolve().parents[1]
        # Update these baselines only for intentional public interface changes.
        expected = {'assets/openband.js': 'ae28ec91a48a93cb469edbf6e044d365917f92b034190429d745b5ba98484dad', 'assets/openband.css': '9dcbb8740ab1106420465d41005cb5f1e5334122cbfa22666042a40ec40bc695', 'index.html': '4a2f8039d273ea2b8287821a81860fd3553eb4a4ad534884de4eb003b738cca6'}
        for filename, digest in expected.items():
            self.assertEqual(hashlib.sha256((root/filename).read_bytes()).hexdigest(),digest,filename)

if __name__=='__main__':unittest.main()
