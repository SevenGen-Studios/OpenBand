"""Financial safety, identity, persistence, source policy and approval regressions."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from tools.filing_review.store import Store,dump,key,ROOT
from tools.filing_review.pipeline import Pipeline
from tools.filing_review.extraction import identify,normalize_money,reconcile,compare
from tools.filing_review.network import PublicHTTP

class FilingReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'site';self.root.mkdir()
        self.band=dict(id=42,iscBandNumber=42,name='Example First Nation',province='XX',filings=[])
        self.data={'bands':[self.band]};self.capital={'bands':{}}
        self.write_data()
        self.s=Store(Path(self.temp.name)/'private');self.addCleanup(self.s.db.close)
        self.s.inventory(self.root,['2024-2025']);self.slot=self.s.rows('slots')[0]
        self.p=Pipeline(self.s,self.root)

    def write_data(self):
        (self.root/'data.json').write_text(dump(self.data));(self.root/'capital-data.json').write_text(dump(self.capital))

    def candidate(self,issues=None):
        cid=self.s.candidate(self.slot['id'],'https://www.canada.ca/a.pdf','https://www.canada.ca/source')
        import hashlib
        raw=b'%PDF-test-evidence';sha=hashlib.sha256(raw).hexdigest();(self.s.pdfs/(sha+'.pdf')).write_bytes(raw)
        self.s.save_candidate(cid,dict(documentValid=True,issues=issues or [],pages=[{'page':1,'text':'evidence'}],
            records=[dict(metric='totalRevenue',value=100,comparative=False,sourcePage=1,sourceReferences=[{'rawValue':'100','pdfPage':1}])],
            documentType='consolidated',pdfUrl='https://www.canada.ca/a.pdf',sourceUrl='https://www.canada.ca/source'),sha=sha)
        return cid

    def test_inventory_idempotent_and_all_provinces(self):
        self.s.inventory(self.root,['2024-2025']);r=self.s.report()
        self.assertEqual(r['counts']['totalExpectedSlots'],1);self.assertEqual(r['slots'][0]['province'],'XX')
        self.assertIn('missing_filing',r['slots'][0]['gaps'])

    def test_configured_range_excludes_historical_slots_without_deleting_them(self):
        self.s.inventory(self.root,['2025-2026'])
        self.assertEqual(self.s.report()['years'],['2025-2026'])
        self.assertEqual(self.s.report()['counts']['totalExpectedSlots'],1)
        self.assertEqual(len(self.s.rows('slots')),2)

    def test_valid_index_never_called_missing(self):
        self.band['filings']=[dict(year='2024-2025',docType='Audited financial statements',href='https://www.canada.ca/a.pdf')]
        self.capital['bands']={'42':{'years':{'2024-2025':dict(parseStatus='parsed',publishable=True,totalRevenue=10,sourceUrl='https://www.canada.ca/a.pdf')}}}
        self.write_data();self.s.inventory(self.root,['2024-2025']);slot=self.s.report()['slots'][0]
        self.assertTrue(slot['existingValid']);self.assertNotIn('missing_filing',slot['gaps']);self.assertIn('original_pdf_not_stored',slot['gaps'])

    def test_comparatives_do_not_create_valid_filing(self):
        self.band['filings']=[dict(year='2024-2025',docType='Audited financial statements',href='https://www.canada.ca/a.pdf')]
        self.capital['bands']={'42':{'years':{'2024-2025':dict(parseStatus='parsed',publishable=True,totalRevenue=10,sourceUrl='x',sourceFiscalYear='2025-2026')}}}
        self.write_data();self.s.inventory(self.root,['2024-2025']);slot=self.s.report()['slots'][0]
        self.assertFalse(slot['existingValid']);self.assertIn('comparative_only',slot['gaps'])

    def test_no_search_is_not_not_publicly_located(self):
        self.assertEqual(self.s.report()['slots'][0]['status'],'Search Pending')
        self.s.search(self.slot['id'],'x','search_incomplete','network unavailable')
        self.assertEqual(self.s.report()['counts']['notPubliclyLocated'],0)

    def test_pending_candidate_not_called_not_located(self):
        self.s.search(self.slot['id'],'x','search_complete','searched')
        self.s.candidate(self.slot['id'],'https://www.canada.ca/a.pdf','https://www.canada.ca/')
        self.assertEqual(self.s.report()['counts']['notPubliclyLocated'],0)

    def test_duplicate_candidate_idempotent(self):
        self.assertEqual(self.candidate(),self.candidate());self.assertEqual(len(self.s.rows('candidates')),1)

    def test_no_automatic_approval(self):
        cid=self.candidate();self.assertEqual(self.s.rows('candidates')[0]['state'],'done')
        with self.assertRaises(ValueError):self.p.import_approved(cid,'admin')

    def test_each_issue_requires_source_resolution(self):
        cid=self.candidate(['figure_disagreement'])
        with self.assertRaises(ValueError):self.p.review(cid,'approve','admin',{'confirmedSourceAndPresentation':True})
        self.p.review(cid,'approve','admin',{'confirmedSourceAndPresentation':True,'resolutions':{'figure_disagreement':{'page':1,'explanation':'The actual current-year column reports 100 dollars.'}}})
        self.assertEqual(self.s.rows('candidates')[0]['state'],'approved')

    def test_wrong_entity_cannot_be_approved(self):
        cid=self.candidate();row=json.loads(self.s.rows('candidates')[0]['payload']);row['documentValid']=False;self.s.save_candidate(cid,row)
        with self.assertRaises(ValueError):self.p.review(cid,'approve','admin',{'confirmedSourceAndPresentation':True})

    def test_existing_values_protected_and_explicit_replacement_historized(self):
        self.capital['bands']={'42':{'name':'Example','years':{'2024-2025':{'totalRevenue':99,'confidence':'high','somePreservedField':7}}}}
        self.write_data();cid=self.candidate();self.p.review(cid,'approve','admin',{'confirmedSourceAndPresentation':True})
        result=self.p.import_approved(cid,'admin');self.assertEqual(result['status'],'replacement_requires_approval')
        self.assertEqual(json.loads((self.root/'capital-data.json').read_text())['bands']['42']['years']['2024-2025']['totalRevenue'],99)
        self.p.import_approved(cid,'admin',True)
        value=json.loads((self.root/'capital-data.json').read_text())['bands']['42']['years']['2024-2025']
        self.assertEqual(value['totalRevenue'],100);self.assertEqual(value['somePreservedField'],7)
        self.assertEqual(self.p.import_approved(cid,'admin')['status'],'already_imported')
        history=self.s.rows('history');self.assertTrue(any(h['action']=='imported' and json.loads(h['previous'])['totalRevenue']==99 for h in history))
        with self.assertRaises(Exception):self.s.db.execute('DELETE FROM history')

    def test_import_does_not_invent_cash_or_debt_mapping(self):
        cid=self.candidate();self.p.review(cid,'approve','admin',{'confirmedSourceAndPresentation':True});self.p.import_approved(cid,'admin')
        value=json.loads((self.root/'capital-data.json').read_text())['bands']['42']['years']['2024-2025']
        self.assertNotIn('cashInvestments',value);self.assertNotIn('debt',value)

    def test_manual_source_correction_preserves_prior_observation(self):
        cid=self.candidate()
        r=self.p.correct_figure(cid,'totalRevenue','(1,234)',1000,1,'Statement of Operations','Actual year column is (1,234), in thousands.','admin')
        self.assertEqual(r['value'],-1234000)
        h=self.s.rows('history')[-1]
        self.assertEqual(json.loads(h['previous'])[0]['value'],100)
        with self.assertRaises(ValueError):self.p.correct_figure(cid,'totalRevenue','1O0',1,1,'Statement of Operations','Ambiguous OCR cannot be normalized.','admin')

    def test_approval_refuses_unlocated_financial_value(self):
        cid=self.candidate();p=json.loads(self.s.rows('candidates')[0]['payload']);p['records'][0]['sourcePage']=None
        self.s.save_candidate(cid,p)
        with self.assertRaises(ValueError):self.p.review(cid,'approve','admin',{'confirmedSourceAndPresentation':True})

    def test_import_checks_original_pdf_checksum(self):
        cid=self.candidate();self.p.review(cid,'approve','admin',{'confirmedSourceAndPresentation':True})
        next(self.s.pdfs.glob('*.pdf')).write_bytes(b'changed')
        with self.assertRaises(ValueError):self.p.import_approved(cid,'admin')

    def test_crash_between_import_files_recovers_idempotently(self):
        cid=self.candidate();self.p.review(cid,'approve','admin',{'confirmedSourceAndPresentation':True})
        import os
        original=os.replace
        def fail_second(source,target):
            if str(target).endswith('/data.json'):raise OSError('simulated interrupted import')
            return original(source,target)
        with patch('os.replace',side_effect=fail_second),self.assertRaises(OSError):self.p.import_approved(cid,'admin')
        self.assertEqual(self.p.import_approved(cid,'admin')['status'],'imported')
        self.assertEqual(len(json.loads((self.root/'data.json').read_text())['bands'][0]['filings']),1)

    def test_private_api_rejects_missing_token_and_untrusted_origin(self):
        from tools.filing_review.server import Handler
        from types import SimpleNamespace
        from unittest.mock import Mock
        h=object.__new__(Handler);h.path='/v1/filing-review/review';h.headers={}
        h.server=SimpleNamespace(token='test-secret',origins={'https://openband.ca'})
        h.response=Mock();h.handle_request(True);self.assertEqual(h.response.call_args.args[0],401)
        h.headers={'Authorization':'Bearer test-secret','Origin':'https://evil.example'}
        h.handle_request(True);self.assertEqual(h.response.call_args.args[0],403)
        h.path='/.openband-ocr/filing-review/review.sqlite';h.handle_request(False);self.assertEqual(h.response.call_args.args[0],404)

    def test_failed_jobs_backoff_and_exhaustion(self):
        cid=self.s.candidate(self.slot['id'],'https://www.canada.ca/a.pdf','https://www.canada.ca/')
        with patch.object(self.p.http,'get',side_effect=RuntimeError('HTTP 429')):
            self.assertTrue(self.p.process_one());self.assertFalse(self.p.process_one())
            self.s.db.execute('UPDATE candidates SET attempts=3,next_try=0');self.s.db.commit();self.assertFalse(self.p.process_one())
        self.assertEqual(self.s.rows('candidates')[0]['state'],'failed')

    def test_expired_lease_recovers(self):
        cid=self.s.candidate(self.slot['id'],'https://www.canada.ca/a.pdf','https://www.canada.ca/')
        self.s.db.execute("UPDATE candidates SET state='processing',lease=0");self.s.db.commit()
        with patch.object(self.p.http,'get',side_effect=RuntimeError('offline')):self.assertTrue(self.p.process_one())
        self.assertEqual(self.s.rows('candidates')[0]['attempts'],1)

    def test_numbers_preserve_signs_and_scale(self):
        self.assertEqual(normalize_money('(1,234.56)',1000),'-1234560.00')
        self.assertEqual(normalize_money('−1,234'),'-1234')
        for raw in ['1O0','I00','1.234','(100','(100)-','(-100)']:
            with self.subTest(raw=raw),self.assertRaises(ValueError):normalize_money(raw)

    def test_disagreement_never_selects_larger_value(self):
        r=dict(metric='totalRevenue',value=-100,sourcePage=2,validationFlags=[])
        other=dict(r,value=100)
        out=compare([r],[other])[0]
        self.assertEqual(out['value'],-100);self.assertEqual(out['verificationStatus'],'manual_review')

    def test_page_disagreement_needs_review(self):
        r=dict(metric='cash',value=100,sourcePage=2,validationFlags=[])
        self.assertEqual(compare([r],[dict(r,sourcePage=3)])[0]['verificationStatus'],'manual_review')

    def test_accounting_adjustments_not_forced(self):
        records=[{'metric':k,'value':v} for k,v in [('totalRevenue',100),('totalExpenses',90),('annualSurplusDeficit',15),('surplusAdjustment',5)]]
        self.assertEqual(reconcile(records)[0]['status'],'passed')
        records.pop();self.assertEqual(reconcile(records)[0]['status'],'review_presentation')

    def test_identity_rejects_corporation_filename_and_wrong_year(self):
        slot=json.loads(self.slot['payload'])
        pages=[dict(page=1,text="Example First Nation Holdings Ltd\nConsolidated financial statements\nMarch 31, 2025\nIndependent Auditor's Report\nIn our opinion present fairly")]
        result=identify(slot,pages,'https://www.canada.ca/Example_First_Nation_2025.pdf')
        self.assertFalse(result['documentValid']);self.assertIn('possible_corporate_entity',result['issues'])
        pages[0]['text']=pages[0]['text'].replace(' Holdings Ltd','').replace('2025','2024')
        self.assertFalse(identify(slot,pages,'https://www.canada.ca/a.pdf')['documentValid'])

    def test_exact_identity_year_and_audit(self):
        slot=json.loads(self.slot['payload']);pages=[dict(page=1,text="Example First Nation\nConsolidated financial statements\nMarch 31, 2025\nIndependent Auditor's Report\nIn our opinion, the financial statements present fairly")]
        self.assertTrue(identify(slot,pages,'https://www.canada.ca/a.pdf')['documentValid'])
        self.assertFalse(identify(slot,pages,'https://www.canada.ca/a.pdf?FY=2023-2024')['documentValid'])

    def test_unapproved_and_private_hosts_blocked(self):
        http=PublicHTTP({'example.test'})
        for url in ['http://www.canada.ca/a.pdf','https://evil.test/a','https://user:pass@www.canada.ca/a','https://www.canada.ca:444/a']:
            with self.subTest(url=url),self.assertRaises(ValueError):http.validate(url)
        with patch('socket.getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443))]),self.assertRaises(ValueError):http.validate('https://example.test/a')

    def test_redirect_target_checked(self):
        h=PublicHTTP()
        with patch.object(h,'permitted',side_effect=[None,ValueError('private')]),patch.object(h,'raw',return_value=(302,{'location':'https://127.0.0.1/a'},b'')),self.assertRaises(ValueError):h.get('https://www.canada.ca/a')

    def test_complete_native_pdf_pipeline_preserves_unavailable_ocr_status(self):
        from tools.filing_review.extraction import extract
        path=ROOT/'research/classification-audit/2026-11-02/sources/378-2024-2025.pdf'
        import hashlib
        raw=path.read_bytes()
        slot=dict(bandId='378',bandNumber=378,name='Carry the Kettle Nakoda Nation',aliases=[],fiscalYear='2024-2025')
        with patch('shutil.which',return_value=None),patch('importlib.util.find_spec',return_value=None):
            result=extract(raw,slot,'https://www.canada.ca/a.pdf',hashlib.sha256(raw).hexdigest())
        self.assertTrue(result['documentValid'])
        self.assertEqual(result['extractionMethod'],'native_pdf')
        self.assertIn('independent_ocr_unavailable',result['issues'])
        self.assertTrue(all(r['verificationStatus']=='manual_review' for r in result['records']))

    def test_actual_parser_keeps_actual_and_comparative_separate(self):
        from tools.bandy_financial import extract_year
        fixture=json.loads((ROOT/'tests/fixtures/bandy-sk/391-2024-2025.json').read_text())
        records,_=extract_year(fixture['document'],fixture['pages'],2025)
        self.assertTrue(records);self.assertTrue(all(not r['comparative'] and r['fiscalYear']=='2024-2025' for r in records))
        self.assertEqual(next(r['value'] for r in records if r['metric']=='totalRevenue'),39879056)

if __name__=='__main__':unittest.main()
