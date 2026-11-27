import copy
import json
import unittest
from datetime import date,timedelta
from unittest.mock import patch
from tools.jobs_collector import listing_is_confirmed_on_source, fetch_source
TODAY=date(2026,11,27)

class ExactPostingRefreshTests(unittest.TestCase):
    def setUp(self):
        self.record={'id':'reviewed','sourceId':'board','title':'Housing Manager','communityId':'293','scope':'community','sourceUrl':'https://employer.test/housing','activeEvidence':{'kind':'open_until_filled'}}
        self.fresh={**self.record,'lastChecked':TODAY.isoformat(),'status':'Date unavailable','verifiedOfficialSource':True,'activeEvidence':{'kind':'open_until_filled','checkedAt':TODAY.isoformat(),'sourceUrl':self.record['sourceUrl']}}
        self.text={'board':'Housing Manager: applications closed. Another job: open until filled.'}

    def test_board_wide_text_cannot_refresh_any_posting(self):
        self.assertFalse(listing_is_confirmed_on_source(self.record,self.text,today=TODAY))

    def test_exact_fresh_posting_can_refresh_a_reviewed_role(self):
        self.assertTrue(listing_is_confirmed_on_source(self.record,self.text,[self.fresh],TODAY))
        suffix={**self.fresh,'title':'Housing Manager – Employment Opportunity'}
        self.assertTrue(listing_is_confirmed_on_source(self.record,self.text,[suffix],TODAY))

    def test_other_role_community_url_stale_or_failed_check_cannot_refresh(self):
        for changes in [{'sourceUrl':'https://employer.test/another'}, {'communityId':'261'}, {'title':'Another Job'}, {'sourceId':'other'}, {'lastChecked':(TODAY-timedelta(days=1)).isoformat()}, {'status':'Closed'}, {'status':'Pending verification'}, {'verifiedOfficialSource':False}, {'activeEvidence':{'kind':'open_until_filled','checkedAt':'2026-11-26','sourceUrl':self.record['sourceUrl']}}, {'activeEvidence':None}]:
            with self.subTest(changes=changes):self.assertFalse(listing_is_confirmed_on_source(self.record,self.text,[{**self.fresh,**changes}],TODAY))
        self.assertFalse(listing_is_confirmed_on_source(self.record,{},[self.fresh],TODAY))

    def test_expired_deadline_does_not_renew_availability(self):
        fresh={**self.fresh,'closingDate':'2026-11-26','activeEvidence':{**self.fresh['activeEvidence'],'kind':'deadline'}}
        self.assertFalse(listing_is_confirmed_on_source(self.record,self.text,[fresh],TODAY))

    def test_collector_attaches_evidence_only_to_successful_detail_fetch(self):
        source={'id':'board','url':'https://employer.test/jobs','name':'Employer','communityIds':['293'],'communityNames':['Swan Lake'],'parser':'job_link_index','inspectDetails':True,'verifiedOfficialSource':True}
        board='<a href="/housing">Housing Manager</a><a href="/other">Support Worker</a>'
        detail={'detailText':'Housing Manager. Open until filled.','status':'Date unavailable'}
        with patch('tools.jobs_collector.fetch_markup',return_value=(board,None)),patch('tools.jobs_collector.inspect_candidate_page',side_effect=[(detail,[]),({},['fetch failed'])]):
            rows,_,text,_=fetch_source(source,TODAY)
        housing=next(r for r in rows if r['sourceUrl'].endswith('/housing'))
        other=next(r for r in rows if r['sourceUrl'].endswith('/other'))
        self.assertEqual(housing['activeEvidence']['kind'],'open_until_filled')
        self.assertNotIn('activeEvidence',other)
        self.assertTrue(listing_is_confirmed_on_source(self.record,{'board':text},rows,TODAY))

    def test_collection_never_renews_from_an_old_candidate_or_index_only(self):
        import tempfile
        from pathlib import Path
        from tools.jobs_collector import collect,normalize_listing
        for include_prior_candidate in [False,True]:
            with self.subTest(prior=include_prior_candidate),tempfile.TemporaryDirectory() as directory:
                root=Path(directory)
                manual={**self.record,'employer':'Nation','manualOverride':True,'verifiedOfficialSource':True,'status':'Open','lastChecked':'2026-10-01'}
                source={'id':'board','name':'Employer','url':'https://employer.test/jobs','communityIds':['293'],'sourceType':'official_employer','verifiedOfficialSource':True}
                previous=[normalize_listing(manual,TODAY)]
                if include_prior_candidate:previous.append(normalize_listing({**self.fresh,'id':'prior','employer':'Nation','manualOverride':False},TODAY))
                for file,payload in [('jobs-sources.json',{'sources':[source]}),('jobs-data.json',{'listings':previous}),('jobs-overrides.json',{'manualListings':[manual]})]:
                    (root/file).write_text(json.dumps(payload))
                with patch('tools.jobs_collector.fetch_source',return_value=([],[],self.text['board'],[])):
                    data,_=collect(root,TODAY)
                row=next(r for r in data['listings'] if r['id']=='reviewed')
                self.assertEqual(row['lastChecked'],'2026-10-01')
                self.assertEqual(row['status'],'Pending verification')

    def test_fresh_closure_with_title_suffix_withdraws_the_manual_job(self):
        import tempfile
        from pathlib import Path
        from tools.jobs_collector import collect,normalize_listing
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            manual={**self.record,'employer':'Nation','manualOverride':True,'verifiedOfficialSource':True,'status':'Open','lastChecked':'2026-11-26'}
            closed={**self.fresh,'id':'found','title':'Housing Manager – Employment Opportunity','employer':'Nation','status':'Closed','extractionConfidence':'high'}
            source={'id':'board','name':'Employer','url':'https://employer.test/jobs','communityIds':['293'],'sourceType':'official_employer','verifiedOfficialSource':True}
            for file,payload in [('jobs-sources.json',{'sources':[source]}),('jobs-data.json',{'listings':[normalize_listing(manual,TODAY)]}),('jobs-overrides.json',{'manualListings':[manual]})]:
                (root/file).write_text(json.dumps(payload))
            with patch('tools.jobs_collector.fetch_source',return_value=([closed],[],self.text['board'],[])):
                data,_=collect(root,TODAY)
            row=next(r for r in data['listings'] if r['id']=='reviewed')
            self.assertEqual(row['status'],'Closed')
            self.assertEqual(row['lastChecked'],TODAY.isoformat())
            self.assertEqual(data['activeCount'],0)
