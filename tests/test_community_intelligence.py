import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from tools.community_history import merge_review_history
from tools.events_discovery import merge_events, is_publishable_event
from tools.jobs_collector import collect, effective_status, title_from_document, validation_warnings


class CommunityIntelligenceTests(unittest.TestCase):
    def test_review_history_retains_old_evidence_without_duplicates(self):
        old=[{'url':'https://example.org/a','reason':'Source unavailable'}]
        new=[old[0],{'url':'https://example.org/b','reason':'Date unclear'}]
        self.assertEqual(merge_review_history(old,new),[old[0],new[1]])
        self.assertEqual(len(old),1)

    def test_event_status_is_recomputed_and_input_not_mutated(self):
        record={'id':'event','bandId':1,'title':'Community gathering','startDate':'2026-10-01',
                'endDate':'2026-10-12','status':'Upcoming','sourceUrl':'https://example.org/gathering',
                'extractionMethod':'json-ld','confidence':1}
        result=merge_events([record],[],date(2026,10,11))
        self.assertEqual(result[0]['status'],'Ongoing')
        self.assertEqual(record['status'],'Upcoming')
        aggregate={**record,'sourceUrl':'https://example.org/events/2026-10-01?shortcode=abc'}
        self.assertFalse(is_publishable_event(aggregate,date(2026,10,11)))

    def test_deadline_cannot_reopen_closed_or_unverified_posting(self):
        base={'closingDate':'2026-12-01','lastChecked':'2026-10-11'}
        for status in ['Closed','Pending verification']:
            self.assertEqual(effective_status({**base,'status':status},date(2026,10,11)),status)
        self.assertEqual(effective_status({**base,'status':'Open','lastChecked':'2026-08-01'},date(2026,10,11)),'Pending verification')
        self.assertEqual(effective_status({**base,'status':'Open'},date(2026,10,11)),'Open')

    def test_source_outage_retains_existing_jobs_without_refreshing_check_date(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            original={'id':'job','title':'Community Health Nurse','employer':'Nation','sourceId':'source',
                      'sourceUrl':'https://example.org/job','communityId':'1','lastChecked':'2026-10-10',
                      'closingDate':'2026-10-20','status':'Open','verifiedOfficialSource':True}
            (root/'jobs-data.json').write_text(json.dumps({'listings':[original]}))
            with patch('tools.jobs_collector.configured_sources',return_value=[{'id':'source','name':'Source','url':'https://example.org/jobs'}]),patch('tools.jobs_collector.fetch_source',return_value=([],['Source unavailable'],'',[])):
                data,_=collect(root,date(2026,10,11))
            self.assertEqual(len(data['listings']),1)
            self.assertEqual(data['listings'][0]['lastChecked'],'2026-10-10')
            self.assertEqual(data['listings'][0]['status'],'Open')

    def test_specific_document_heading_wins_over_body_text(self):
        text='Employment Opportunity\nChild and Family Services Lead\nFull-Time Term contract- 12 months\nTreaty Six First Nations (CT6FN). This position reports directly to the Director of Policy.'
        self.assertEqual(title_from_document(text),'Child and Family Services Lead')
        self.assertIn('A specific job title has not been verified',validation_warnings({'title':'Job board','employer':'Nation','sourceUrl':'https://example.org/jobs'}))

    def test_reviewed_job_fields_survive_an_offline_refresh(self):
        root=Path(__file__).resolve().parents[1]
        data,_=collect(root,date(2026,10,11),offline=True)
        job=next(row for row in data['listings'] if row.get('sourceVerification'))
        self.assertEqual(job['title'],'Child and Family Services Lead')
        self.assertEqual(job['salary'],'$65,000–$70,000')
        self.assertEqual(job['closingDate'],'2026-10-19')
        self.assertEqual(job['sourceVerification']['sourcePages'],[1,2])


if __name__=='__main__':unittest.main()
