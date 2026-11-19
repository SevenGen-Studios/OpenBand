import gzip
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from tools.apply_community_enrichment import validate
from tools.events_discovery import extract_html_events, is_publishable_event
from tools.jobs_collector import career_table_candidates, collect, posting_key
from tools.news_discovery import article_page_metadata, direct_article_candidate, extract_document_text
from tools.research_public_sources import research, source_checks

ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = ROOT / 'research/community-intelligence/coverage-expansion-2026-11-03'
TODAY = date(2026, 11, 3)


def notice_pdf(text):
    stream = f'BT /F1 12 Tf 35 750 Td ({text}) Tj ET'.encode()
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>', b'<< /Length '+str(len(stream)).encode()+b' >>\nstream\n'+stream+b'\nendstream']
    body = b'%PDF-1.4\n'; offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(body)); body += f'{i} 0 obj\n'.encode()+obj+b'\nendobj\n'
    xref = len(body); body += b'xref\n0 6\n0000000000 65535 f \n'
    body += b''.join(f'{n:010d} 00000 n \n'.encode() for n in offsets[1:])
    return body+f'trailer << /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF'.encode()


class CoverageExpansionTests(unittest.TestCase):
    def test_embedded_pdf_text_without_command_line_tools(self):
        text = 'Official First Nation notice. Applications close November 13, 2026. Community Health Representative employment opportunity.'
        class Fetcher:
            def get(self, url): return notice_pdf(text), url, 'application/pdf'
        with patch('tools.news_discovery.shutil.which', return_value=None):
            found, method, _ = extract_document_text(Fetcher(), 'https://example.test/notice.pdf')
        self.assertEqual(method, 'pdf_text')
        self.assertIn('November 13, 2026', found)
        self.assertIn('Community Health Representative', found)

    def test_bad_pdf_remains_unavailable_without_ocr(self):
        class Fetcher:
            def get(self, url): return b'%PDF-invalid', url, 'application/pdf'
        with patch('tools.news_discovery.shutil.which', return_value=None):
            text, method, _ = extract_document_text(Fetcher(), 'https://example.test/notice.pdf')
        self.assertEqual((text, method), ('', 'ocr_unavailable'))

    def test_career_table_deadlines_do_not_bleed_between_rows(self):
        markup = '''<table><thead><tr><th>Opportunity</th><th>Posted on</th><th>Type</th><th>Term</th><th>Closing Date</th></tr></thead><tbody>
        <tr><td><a href="/job-postings/worker">Program Worker</a></td><td>2026-11-01</td><td>Full-Time</td><td>Term</td><td>2026-11-06</td></tr>
        <tr><td><a href="/job-postings/clerk">Office Clerk</a></td><td>2026-11-02</td><td>Part-Time</td><td>Term</td><td></td></tr>
        <tr><td><a href="/job-postings/driver">Van Driver</a></td><td>2026-10-01</td><td>Full-Time</td><td>Term</td><td>2026-10-30</td></tr>
        <tr><td><a href="https://other.test/job">External Worker</a></td><td>2026-11-01</td><td></td><td></td><td>2026-12-01</td></tr></tbody></table>'''
        source = {'id':'test', 'name':'First Nation', 'url':'https://example.test/careers', 'communityIds':['1'], 'communityNames':['First Nation'], 'verifiedOfficialSource':True}
        rows, warnings = career_table_candidates(markup, source, TODAY)
        self.assertFalse(warnings); self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]['closingDate'], '2026-11-06')
        self.assertEqual(rows[0]['postedDate'], '2026-11-01')
        self.assertEqual(rows[1]['status'], 'Pending verification')
        self.assertIsNone(rows[1]['closingDate'])
        self.assertEqual(rows[2]['status'], 'Closed')
        self.assertFalse(career_table_candidates(markup, {**source, 'communityIds':['1','2']}, TODAY)[0])

    def test_same_posting_title_suffix_merges_but_distinct_roles_do_not(self):
        base = {'title':'Recreation Assistant', 'sourceUrl':'https://example.test/2026/10/recreation-assistant/', 'communityId':'1'}
        self.assertEqual(posting_key(base), posting_key({**base,'title':'Recreation Assistant – Term Opportunity'}))
        self.assertNotEqual(posting_key(base), posting_key({**base,'title':'Nurse'}))
        self.assertNotEqual(posting_key(base), posting_key({**base,'sourceUrl':'https://example.test/other-job'}))

    def test_duplicate_posting_preserves_manual_details(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            base={'id':'auto','title':'Recreation Assistant – Term Opportunity','communityId':'1','sourceUrl':'https://example.test/2026/10/assistant','employer':'First Nation','closingDate':'2026-11-10','lastChecked':'2026-11-03','status':'Open','verifiedOfficialSource':True,'extractionConfidence':'high'}
            manual={**base,'id':'manual','title':'Recreation Assistant','salary':'$25 per hour','manualOverride':True}
            for name,data in {'data.json':{'bands':[{'id':1,'name':'First Nation','province':'SK'}]},'jobs-data.json':{'listings':[base]},'jobs-sources.json':{'sources':[]},'jobs-overrides.json':{'manualListings':[manual]}}.items():
                (root/name).write_text(json.dumps(data))
            data,report=collect(root,TODAY,offline=True)
            self.assertEqual(len(data['listings']),1)
            self.assertEqual(data['listings'][0]['id'],'manual')
            self.assertEqual(data['listings'][0]['salary'],'$25 per hour')
            self.assertGreaterEqual(report['duplicatesSuppressed'],1)

    def test_issued_date_is_publication_but_modified_date_is_not(self):
        markup='<h1>First Nation water project announcement</h1><meta name="dcterms.issued" content="2026-09-09"><meta name="dcterms.modified" content="2026-11-03">'
        self.assertEqual(article_page_metadata(markup,'https://www.canada.ca/en/news/2026/09/project.html')['published'],'2026-09-09')
        self.assertIsNone(article_page_metadata(markup.replace('dcterms.issued','unrelated'),'https://example.test/news')['published'])
        row=direct_article_candidate(markup,'https://www.canada.ca/en/news/2026/09/project.html',{'bandId':1,'communityName':'First Nation','provinceTerritory':'SK'},{'type':'Government Source','name':'Government of Canada','requiresCommunityMention':False})
        self.assertEqual(row['dateSource'],'meta:dcterms.issued')

    def test_calendar_day_navigation_is_not_an_event(self):
        row={'title':'2 events, 3 Testing Tuesdays November 3', 'description':'Event date: November 3, 2026','sourceUrl':'https://example.test/calendar/2026-11-03','startDate':'2026-11-03','extractionMethod':'html'}
        self.assertFalse(is_publishable_event(row,TODAY))

    def test_archived_health_calendar_preserves_distinct_occurrences(self):
        checks=json.loads((CAMPAIGN/'source-checks.json').read_text());url='https://siksikahealth.com/calendar/';body=gzip.decompress((ROOT/checks[url]['evidencePath']).read_bytes()).decode()
        rows,_,_=extract_html_events(body,url,{'bandId':430,'communityName':'Siksika Nation','provinceTerritory':'AB'},{'name':'Siksika Health Services','type':'Official First Nation Website','status':'verified','requiresCommunityMention':False},TODAY)
        self.assertEqual(len(rows),30)
        self.assertTrue(all(r['extractionMethod']=='json-ld' for r in rows))
        self.assertGreaterEqual(len({r['startDate'] for r in rows if r['title']=='Wellbriety'}),4)

    def test_reviewed_records_have_intact_evidence_and_explicit_associations(self):
        records=json.loads((CAMPAIGN/'reviewed-enrichment.json').read_text())['records']
        roster={str(b['id']) for b in json.loads((ROOT/'data.json').read_text())['bands']}
        for entry in records:
            with self.subTest(id=entry['record']['id']):validate(entry,roster,{},ROOT,TODAY)

    def test_research_campaign_cannot_escape_its_directory(self):
        with self.assertRaises(ValueError):research(ROOT,[],campaign='../outside')

    def test_campaign_diagnostics_keep_last_success_after_a_later_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);base=root/'research/community-intelligence'
            for campaign,record in [('first',{'status':'checked','lastAttempted':'2026-11-03T12:00:00Z','lastSuccess':'2026-11-03T12:00:00Z','sha256':'evidence'}),('second',{'status':'unavailable','lastAttempted':'2026-11-03T13:00:00Z'})]:
                path=base/campaign;path.mkdir(parents=True);(path/'source-checks.json').write_text(json.dumps({'https://example.test/':record}))
            result=source_checks(root)['https://example.test/']
            self.assertEqual(result['status'],'unavailable')
            self.assertEqual(result['lastSuccess'],'2026-11-03T12:00:00Z')
            self.assertEqual(result['sha256'],'evidence')

    def test_source_registration_retains_reviewed_job_adapter(self):
        from tools.register_community_sources import register
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            payloads={
                'data.json':{'bands':[{'id':1,'name':'First Nation','province':'SK'}]},
                'community-research-sources.json':{'sources':[{'id':'careers','url':'https://example.test/careers','communityIds':['1'],'categories':['jobs'],'name':'First Nation','type':'Official First Nation Website','verifiedAt':'2026-11-03','jobParser':'career_table','maxDetailPages':12}]},
                'news-sources.json':{'communities':[]},'events-sources.json':{'communities':[]},
                'jobs-sources.json':{'sources':[{'id':'existing','url':'https://example.test/careers','communityIds':['1'],'parser':'job_link_index','customField':'preserve'}]}}
            for name,data in payloads.items():(root/name).write_text(json.dumps(data))
            register(root);register(root)
            sources=json.loads((root/'jobs-sources.json').read_text())['sources']
            self.assertEqual(len(sources),1)
            self.assertEqual(sources[0]['parser'],'career_table')
            self.assertEqual(sources[0]['maxDetailPages'],12)
            self.assertEqual(sources[0]['customField'],'preserve')


class BreadthPipelineTests(unittest.TestCase):
    def test_explicit_employer_open_deadline_variants(self):
        from tools.jobs_collector import OPEN_UNTIL_FILLED
        for phrase in ['Open until filled', 'Until Suitable Candidate is Found',
                       'Until a suitable candidate is found', 'Open Until Position is Filled']:
            self.assertIsNotNone(OPEN_UNTIL_FILLED.search(phrase), phrase)
        for phrase in ['Suitable candidates should apply', 'This position is filled',
                       'Applications are welcome', 'Check back for future opportunities']:
            self.assertIsNone(OPEN_UNTIL_FILLED.search(phrase), phrase)

    def test_audit_meeting_is_an_event_but_report_is_not(self):
        base = {'title':'Audit & program update community meeting',
                'description':'Date: November 24, 2026. Public community meeting.',
                'startDate':'2026-11-24', 'sourceUrl':'https://example.test/meetings/november',
                'extractionMethod':'reviewed-source'}
        self.assertTrue(is_publishable_event(base, date(2026,11,4)))
        self.assertFalse(is_publishable_event({**base, 'title':'Annual audit report'}, date(2026,11,4)))
        self.assertFalse(is_publishable_event({**base, 'description':'Audit report available for download.'}, date(2026,11,4)))

    def test_image_evidence_uses_installed_ocr_fallback(self):
        from tools.research_public_sources import evidence_text
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); (root/'poster.gz').write_bytes(gzip.compress(b'image-fixture'))
            check={'contentType':'image/png','evidencePath':'poster.gz','url':'https://example.test/poster.png'}
            def read_image(path):
                self.assertEqual(Path(path).read_bytes(), b'image-fixture')
                return 'Public community meeting November 24, 2026'
            with patch('shutil.which', return_value=None), patch('tools.local_ocr._rapidocr_text', side_effect=read_image):
                self.assertIn('November 24, 2026', evidence_text(root, check))

    def test_repeated_meeting_dates_are_distinct_and_exact_duplicate_is_suppressed(self):
        import hashlib
        from tools.apply_community_enrichment import apply
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); checks=root/'research/community-intelligence/phase2-2026-11-02'; checks.mkdir(parents=True)
            body=b'<p>Example First Nation community meetings November 24 and 25, 2026</p>'
            (root/'proof.gz').write_bytes(gzip.compress(body))
            proof={'url':'https://example.test/community-meetings','status':'checked','evidencePath':'proof.gz',
                   'sha256':hashlib.sha256(body).hexdigest(),'lastSuccess':'2026-11-04T12:00:00Z',
                   'contentType':'text/html','terms':['Example First Nation','community meetings']}
            entries=[]
            for id,day in [('first',24),('second',25),('duplicate',25)]:
                record={'id':id,'bandId':1,'title':'Community meeting','startDate':f'2026-11-{day}',
                        'description':f'Date: November {day}, 2026. Community meeting.',
                        'sourceUrl':proof['url'],'extractionMethod':'reviewed-source'}
                entries.append({'kind':'events','reviewStatus':'reviewed','record':record,'evidence':[proof],
                                'communityEvidence':{'1':['Example First Nation']}})
            fixtures={'data.json':{'bands':[{'id':1}]},'community-enrichment.json':{'records':entries},
                      'news-data.json':{'articles':[]},'events-data.json':{'events':[]},
                      'projects-data.json':{'projects':[]},'jobs-overrides.json':{'manualListings':[]}}
            for name,payload in fixtures.items(): (root/name).write_text(json.dumps(payload))
            (checks/'source-checks.json').write_text('{}')
            result=apply(root, date(2026,11,4))
            self.assertEqual([r['action'] for r in result], ['added','added','duplicate_suppressed'])
            self.assertEqual([r['startDate'] for r in json.loads((root/'events-data.json').read_text())['events']], ['2026-11-24','2026-11-25'])


class ResearchOcrConsistencyTests(unittest.TestCase):
    def test_pinned_engine_is_used_even_when_tesseract_is_installed(self):
        from tools.research_public_sources import evidence_text
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); (root/'poster.gz').write_bytes(gzip.compress(b'poster'))
            check={'contentType':'image/png','evidencePath':'poster.gz','url':'https://example.test/poster.png'}
            with patch('shutil.which', return_value='/usr/bin/tesseract'), patch('tools.local_ocr._rapidocr_text', return_value='reviewed poster text') as ocr, patch('subprocess.check_output') as command:
                self.assertEqual(evidence_text(root, check), 'reviewed poster text')
                ocr.assert_called_once(); command.assert_not_called()
