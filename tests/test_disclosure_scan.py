from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs,urlsplit

from tools.disclosure_scan import (fiscal_years,valid_years,scan_one,reconcile_all,
    validate_transition,run,publish,protected_digest,json_bytes,recover_publication)

YEAR='2023-2024'
KIND='Audited consolidated financial statements'


def band(bid=394,province='SK'):
    return dict(id=bid,iscBandNumber=bid,name=f'Nation {bid}',province=province,filings=[dict(year=YEAR,docType=KIND,date='Not yet posted',posted=False,href=None,people=[],parse_status='not_required')])


def source_page(bid,year=YEAR):
    return (f'<html><main>Number {bid}<table><tr><td>{year}</td><td><a href="DisplayBinaryData.aspx?BAND_NUMBER_FF={bid}&amp;FY={year}&amp;DOC=Audited%20consolidated%20financial%20statements&amp;lang=eng">{KIND}</a></td><td>2026-09-03</td></tr></table></main></html>').encode()

class HTTP:
    def __init__(self):self.calls=[]
    def get(self,url,**kwargs):
        bid=int(parse_qs(urlsplit(url).query)['BAND_NUMBER'][0]);self.calls.append(bid)
        return source_page(bid),url

class DisclosureScanTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.data_path=self.root/'data.json';self.state=self.root/'state'
        self.state.mkdir();self.data={'generated':'before','bands':[band()]}
        self.data_path.write_bytes(json_bytes(self.data));self.report_path=self.root/'report.json'

    def scan(self,**kwargs):
        return run(self.data_path,self.report_path,self.state,[YEAR],http=kwargs.pop('http',HTTP()),**kwargs)

    def test_all_database_profiles_and_future_provinces_are_included(self):
        data={'bands':[band(394,'SK'),band(500,'AB'),band(300,'MB'),band(600,'ON'),dict(band(462,'AB'),id='separate-government',sharedIscIdentity=True),dict(band(900,'BC'),iscBandNumber=None)]}
        self.data_path.write_bytes(json_bytes(data));http=HTTP();r=self.scan(http=http)
        self.assertEqual(r['profilesReviewed'],6);self.assertEqual(r['profilesExpected'],6)
        self.assertEqual(r['profilesChecked'],4);self.assertEqual(r['identityReviews'],2)
        self.assertEqual(http.calls,[394,500,300,600])

    def test_all_profiles_scan_promotes_only_metadata_and_is_idempotent(self):
        r=self.scan(write=True);after=json.loads(self.data_path.read_text())
        self.assertEqual(r['documentsRecovered'],1);f=after['bands'][0]['filings'][0]
        self.assertTrue(f['posted']);self.assertEqual(f['people'],[]);self.assertTrue(f['manual_review_required'])
        second=self.scan(write=True);self.assertEqual(second['documentsRecovered'],0)
        self.assertEqual(len(json.loads(self.data_path.read_text())['bands'][0]['filings']),1)

    def test_dry_run_leaves_dataset_byte_identical(self):
        before=self.data_path.read_bytes();r=self.scan()
        self.assertEqual(r['documentsRecovered'],1);self.assertFalse(r['metadataApplied'])
        self.assertEqual(before,self.data_path.read_bytes())

    def test_resume_uses_successful_recent_checks_but_retries_failures(self):
        first=HTTP();self.scan(http=first)
        second=HTTP();self.scan(http=second,resume=True);self.assertEqual(second.calls,[])
        self.scan(http=second);self.assertEqual(second.calls,[394])

    def test_resume_refuses_stale_cache_and_identity_changes(self):
        self.scan();checkpoint=self.state/'checkpoint.json';c=json.loads(checkpoint.read_text());c['startedAt']='2020-01-01T00:00:00+00:00';checkpoint.write_bytes(json_bytes(c))
        http=HTTP();self.scan(http=http,resume=True);self.assertEqual(http.calls,[394])
        data=json.loads(self.data_path.read_text());data['bands'][0]['iscBandNumber']=395;self.data_path.write_bytes(json_bytes(data))
        http=HTTP();self.scan(http=http,resume=True);self.assertEqual(http.calls,[395])

    def test_access_failure_never_downgrades_existing_filing(self):
        original=band();original['filings'][0].update(posted=True,href='https://example.test/verified.pdf',people=[{'name':'Verified','remuneration':100}],parse_status='ok_pdf_text')
        self.data={'bands':[original]};self.data_path.write_bytes(json_bytes(self.data));before=self.data_path.read_bytes()
        class Blocked:
            def get(self,*a,**k):raise PermissionError('robots.txt disallows this URL')
        r=self.scan(write=True,http=Blocked());self.assertEqual(r['sourceFailures'],1);self.assertEqual(len(r['results'][0]['attempts']),1)
        self.assertEqual(r['documentsRecovered'],0);self.assertEqual(self.data_path.read_bytes(),before)

    def test_transient_source_failures_retry_with_backoff(self):
        class Temporary:
            def __init__(self):self.count=0
            def get(self,url,**kw):
                self.count+=1
                if self.count<3:raise TimeoutError('timed out')
                return source_page(394),url
        h=Temporary();waits=[];row=scan_one(band(),h,[YEAR],sleep=waits.append)
        self.assertEqual(row['status'],'checked');self.assertEqual(waits,[2,4]);self.assertEqual(len(row['attempts']),3)

    def test_retry_after_is_honored_or_source_deferred(self):
        from tools.filing_review.network import HTTPStatusError
        class Throttled:
            def __init__(self,delay):self.count=0;self.delay=delay
            def get(self,url,**kw):
                self.count+=1
                if self.count==1:raise HTTPStatusError(429,self.delay)
                return source_page(394),url
        waits=[];h=Throttled('10');result=scan_one(band(),h,[YEAR],sleep=waits.append)
        self.assertEqual(result['status'],'checked');self.assertEqual(waits,[10])
        waits=[];h=Throttled('120');result=scan_one(band(),h,[YEAR],sleep=waits.append)
        self.assertEqual(result['status'],'source_unavailable');self.assertEqual(h.count,1);self.assertEqual(waits,[])

    def test_wrong_band_source_and_access_denial_do_not_retry(self):
        class Wrong:
            def get(self,url,**kw):return source_page(395),url
        waits=[];r=scan_one(band(),Wrong(),[YEAR],sleep=waits.append)
        self.assertEqual(r['status'],'source_unavailable');self.assertEqual(waits,[])

    def test_unparsed_source_links_require_review_instead_of_empty_success(self):
        class ChangedLayout:
            def get(self,url,**kw):
                return b'<main>Number 394 <a href="DisplayBinaryData.aspx?BAND_NUMBER_FF=394&amp;FY=2023-2024&amp;DOC=Audited%20consolidated%20financial%20statements">Audit</a></main>',url
        row=scan_one(band(),ChangedLayout(),[YEAR])
        self.assertEqual(row['status'],'source_unavailable')
        self.assertIn('could not be parsed',row['error'])

    def test_existing_posted_sources_and_people_cannot_be_changed(self):
        b=band();b['filings'][0].update(posted=True,href='https://example.test/verified.pdf',people=[{'name':'Verified','remuneration':100}])
        row=scan_one(b,HTTP(),[YEAR]);before={'bands':[b]};after,updates,warnings=reconcile_all(before,[row],[YEAR])
        self.assertEqual(before,after);self.assertEqual(updates,[]);self.assertTrue(warnings)
        after['bands'][0]['filings'][0]['people'][0]['remuneration']=999
        with self.assertRaises(ValueError):validate_transition(before,after,[row],[YEAR])

    def test_partial_source_failures_do_not_block_confirmed_metadata_recovery(self):
        data={'bands':[band(394),band(395)]};self.data_path.write_bytes(json_bytes(data))
        class Partial(HTTP):
            def get(self,url,**kw):
                if 'BAND_NUMBER=395&' in url:raise PermissionError('restricted')
                return super().get(url,**kw)
        r=self.scan(write=True,http=Partial());self.assertEqual(r['profilesReviewed'],2);self.assertEqual(r['sourceFailures'],1)
        after=json.loads(self.data_path.read_text());self.assertTrue(after['bands'][0]['filings'][0]['posted']);self.assertFalse(after['bands'][1]['filings'][0]['posted'])

    def test_preservation_baseline_advances_only_after_scoped_validation(self):
        baseline=self.root/'baseline.json';before={'files':{'data.json':protected_digest(self.data),'capital-data.json':'untouched'}};baseline.write_bytes(json_bytes(before))
        history=self.root/'history.jsonl';r=self.scan(write=True,baseline_path=baseline,history_path=history)
        new=json.loads(baseline.read_text());self.assertEqual(new['files']['capital-data.json'],'untouched')
        self.assertEqual(new['files']['data.json'],protected_digest(json.loads(self.data_path.read_text())))
        event=json.loads(history.read_text());self.assertEqual(len(event['updates']),1)
        self.scan(write=True,baseline_path=baseline,history_path=history);self.assertEqual(len(history.read_text().splitlines()),1)

    def test_unrelated_prior_baseline_change_blocks_publication(self):
        baseline=self.root/'baseline.json';baseline.write_bytes(json_bytes({'files':{'data.json':'unexpected'}}));before=self.data_path.read_bytes()
        with self.assertRaises(ValueError):self.scan(write=True,baseline_path=baseline)
        self.assertEqual(before,self.data_path.read_bytes())

    def test_concurrent_dataset_edit_is_not_overwritten(self):
        row=scan_one(band(),HTTP(),[YEAR]);after,updates,_=reconcile_all(self.data,[row],[YEAR]);old=self.data_path.read_bytes()
        self.data_path.write_text('{"someone":"else"}')
        with self.assertRaises(ValueError):publish(self.data_path,old,after,[row],[YEAR],updates,self.state)
        self.assertEqual(json.loads(self.data_path.read_text()),{'someone':'else'})

    def test_interrupted_multi_file_publication_resumes_without_duplicate_history(self):
        baseline=self.root/'baseline.json';baseline.write_bytes(json_bytes({'files':{'data.json':protected_digest(self.data)}}));history=self.root/'history.jsonl'
        import tools.disclosure_scan as scan
        original=scan.atomic
        def fail(path,raw):
            if Path(path).resolve()==baseline.resolve():raise OSError('interrupted')
            return original(path,raw)
        with patch.object(scan,'atomic',side_effect=fail),self.assertRaises(OSError):self.scan(write=True,baseline_path=baseline,history_path=history)
        recover_publication(self.state,{p.resolve() for p in (self.data_path,baseline,history)})
        self.assertTrue(json.loads(self.data_path.read_text())['bands'][0]['filings'][0]['posted'])
        self.assertEqual(len(history.read_text().splitlines()),1)
        self.scan(write=True,baseline_path=baseline,history_path=history,resume=True)
        self.assertEqual(len(history.read_text().splitlines()),1)

    def test_recovery_refuses_different_destinations(self):
        (self.state/'publication.json').write_bytes(json_bytes({'status':'pending','files':[{'path':'/other/data.json','staged':'one.json','before':None,'after':'x'}]}))
        with self.assertRaises(ValueError):recover_publication(self.state,{self.data_path.resolve()})

    def test_five_year_window_and_configurable_ranges(self):
        self.assertEqual(fiscal_years(2026),['2021-2022','2022-2023','2023-2024','2024-2025','2025-2026'])
        self.assertEqual(valid_years(['2023-2024','2023-2024']),['2023-2024'])
        for years in [[],['2023-2025'],['2024/25']]:
            with self.assertRaises(ValueError):valid_years(years)

if __name__=='__main__':unittest.main()
