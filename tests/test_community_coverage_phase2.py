import copy
import gzip
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from tools.apply_community_enrichment import validate
from tools.community_coverage import inventory
from tools.events_discovery import extract_eventer_detail, is_publishable_event
from tools.jobs_collector import scoped_job_candidates, source_check_metadata, extract_labeled_date, fetch_markup, effective_status, fetch_source, collect
from tools.news_discovery import direct_article_candidate

ROOT=Path(__file__).resolve().parents[1]
TODAY=date(2026,11,3)
BEFORE=ROOT/'research/community-intelligence/phase2-2026-11-02/before'


class ReviewedEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entries=json.loads((ROOT/'community-enrichment.json').read_text())['records']
        cls.roster={str(b['id']) for b in json.loads((ROOT/'data.json').read_text())['bands']}
        cls.checks=json.loads((ROOT/'research/community-intelligence/phase2-2026-11-02/source-checks.json').read_text())

    def test_every_reviewed_assertion_is_supported_by_its_archived_primary_source(self):
        for entry in self.entries:
            with self.subTest(id=entry['record']['id']):validate(entry,self.roster,self.checks,ROOT,TODAY)

    def test_known_but_wrong_province_community_cannot_replace_reviewed_association(self):
        entry=copy.deepcopy(next(e for e in self.entries if e['record']['id']=='sayisi-dene-microgrid'))
        entry['record']['firstNationIds']=['406']
        with self.assertRaisesRegex(ValueError,'community evidence'):validate(entry,self.roster,self.checks,ROOT,TODAY)

    def test_funding_announcement_cannot_be_silently_marked_complete(self):
        entry=copy.deepcopy(next(e for e in self.entries if e['record']['id']=='sayisi-dene-microgrid'))
        entry['record']['status']='Completed'
        with self.assertRaisesRegex(ValueError,'status differs'):validate(entry,self.roster,self.checks,ROOT,TODAY)

    def test_partnership_option_is_not_an_exercised_ownership_percentage(self):
        entry=copy.deepcopy(next(e for e in self.entries if e['record']['id']=='ncn-wuskwatim-partnership'))
        entry['record']['ownershipPercentage']=33
        with self.assertRaisesRegex(ValueError,'Ownership percentage'):validate(entry,self.roster,self.checks,ROOT,TODAY)

    def test_publisher_date_cannot_be_replaced_with_event_date(self):
        entry=copy.deepcopy(next(e for e in self.entries if e['kind']=='news'))
        entry['record']['publishedAt']='2026-11-01'
        with self.assertRaisesRegex(ValueError,'Publication metadata'):validate(entry,self.roster,self.checks,ROOT,TODAY)

    def test_research_lead_cannot_enter_published_data(self):
        entry=copy.deepcopy(self.entries[0]);entry['reviewStatus']='pending'
        with self.assertRaisesRegex(ValueError,'Research leads'):validate(entry,self.roster,self.checks,ROOT,TODAY)

    def test_existing_projects_and_audit_disclosures_survive_enrichment_unchanged(self):
        before=json.loads(gzip.decompress((BEFORE/'projects-data.json.gz').read_bytes()))
        after=json.loads((ROOT/'projects-data.json').read_text())
        for field in ('projects','verifiedPartnerships','financialDisclosures','unverifiedProjects'):
            lookup={r['id']:r for r in after[field]}
            for row in before[field]:self.assertEqual(row,lookup[row['id']],(field,row['id']))

    def test_financial_guard_allows_independent_feeds_but_preserves_financial_fingerprints(self):
        from tools.manitoba_baseline import verify
        baseline={'protectedIds':['1'],'provinceCounts':{'SK':1},'files':{'data.json':'financial-original','news-data.json':'old','projects-data.json':'old','jobs-data.json':'old'}}
        current={**baseline,'files':{**baseline['files'],'news-data.json':'new','projects-data.json':'new','jobs-data.json':'new'}}
        with patch('tools.manitoba_baseline.snapshot',return_value=current):self.assertEqual(verify(baseline),current)
        current['files']['data.json']='unexpected financial mutation'
        with patch('tools.manitoba_baseline.snapshot',return_value=current):
            with self.assertRaisesRegex(ValueError,'data.json'):verify(baseline)

    def test_prior_news_record_ids_are_retained(self):
        before=json.loads(gzip.decompress((BEFORE/'news-data.json.gz').read_bytes()))
        after=json.loads((ROOT/'news-data.json').read_text())
        self.assertTrue({r['id'] for r in before['articles']} <= {r['id'] for r in after['articles']})

    def test_project_costs_and_beneficiary_roles_remain_distinct(self):
        rows={r['id']:r for r in json.loads((ROOT/'projects-data.json').read_text())['projects']}
        self.assertNotIn('estimatedCost',rows['valley-fiber-mb-99017'])
        self.assertIn('beneficiaries',rows['valley-fiber-mb-99017']['relationshipType'].lower())
        self.assertNotIn('ownershipPercentage',rows['ncn-wuskwatim-partnership'])
        self.assertEqual(rows['yellow-quill-ten-homes']['completionDate'],'2024')
        self.assertNotEqual(rows['poundmaker-lagoon-upgrades']['status'],'Completed')

    def test_coverage_counts_all_communities_and_only_confirmed_active_jobs(self):
        report=inventory(ROOT,TODAY)
        self.assertEqual(len(report['communities']),len(self.roster))
        self.assertEqual({p:r['tracked'] for p,r in report['byProvince'].items()},{'SK':69,'AB':48,'MB':63})
        row=next(r for r in report['communities'] if r['communityId']=='317')
        self.assertGreater(row['activeJobs'],0)
        self.assertIn('not established',row['emptyResultMeaning'])
        self.assertTrue(any(s['lastSuccess'] for r in report['communities'] for s in r['sources'] if s['category']=='news'))


def card(id,title,place,deadline,url):
    return f'<div class="job-item"><div class="job-title" id="job-{id}"><h3>{title}</h3><p>{place}</p><p><b>Deadline:</b> {deadline}</p></div><div class="job-content"><a href="{url}">DOWNLOAD</a></div></div>'


class ScopedEmploymentTests(unittest.TestCase):
    def setUp(self):
        self.source={'id':'schools','name':'Official school system','url':'https://school.test/careers/','verifiedOfficialSource':True,
                     'communityAliasesById':{'261':['Brokenhead Ojibway Nation'],'284':['Birdtail Sioux Dakota Nation']},
                     'communityNamesById':{'261':'Brokenhead Ojibway Nation','284':'Birdtail Sioux'}}

    def test_current_official_card_is_evidence_even_when_document_is_robots_restricted(self):
        html=card(1,'Grade 9 Teacher','Brokenhead Ojibway Nation','Open until Filled','/posting.pdf')
        with patch('tools.jobs_collector.extract_document_text',return_value=('', 'fetch_failed','robots.txt disallows source')):
            rows,reviews=scoped_job_candidates(html,self.source,TODAY)
        self.assertEqual(rows[0]['status'],'Open');self.assertEqual(rows[0]['communityId'],'261')
        self.assertEqual(rows[0]['sourceUrl'],'https://school.test/careers/#job-1')
        self.assertEqual(rows[0]['activeEvidence']['documentStatus'],'unavailable')
        self.assertEqual(reviews[0]['status'],'document_unavailable')

    def test_deadline_and_community_cannot_leak_from_adjacent_cards(self):
        html=card(1,'Teacher','Brokenhead Ojibway Nation','Open until Filled','/one.pdf')+card(2,'Nurse','Birdtail Sioux Dakota Nation','Not stated','/two.pdf')
        with patch('tools.jobs_collector.extract_document_text',return_value=('', 'fetch_failed','robots.txt disallows source')):
            rows,_=scoped_job_candidates(html,self.source,TODAY)
        self.assertEqual([(r['title'],r['communityId']) for r in rows],[('Teacher','261')])

    def test_generic_or_multi_community_cards_do_not_fan_out_to_every_nation(self):
        html=card(1,'Regional Coordinator','Winnipeg','Open until Filled','/one.pdf')+card(2,'Teacher','Brokenhead Ojibway Nation and Birdtail Sioux Dakota Nation','Open until Filled','/two.pdf')
        with patch('tools.jobs_collector.extract_document_text') as fetch:
            rows,_=scoped_job_candidates(html,self.source,TODAY)
        self.assertEqual(rows,[]);fetch.assert_not_called()

    def test_explicit_closed_document_overrules_open_board_card(self):
        html=card(1,'Teacher','Brokenhead Ojibway Nation','Open until Filled','/one.pdf')
        with patch('tools.jobs_collector.extract_document_text',return_value=('Teacher. Closing Date: October 20, 2026','pdf_text',None)):
            rows,_=scoped_job_candidates(html,self.source,TODAY)
        self.assertEqual(rows[0]['status'],'Closed')

    def test_unverified_board_cannot_automatically_publish_undated_jobs(self):
        html=card(1,'Teacher','Brokenhead Ojibway Nation','Open until Filled','/one.pdf')
        with patch('tools.jobs_collector.extract_document_text',return_value=('', 'failed','unavailable')):
            rows,_=scoped_job_candidates(html,{**self.source,'verifiedOfficialSource':False},TODAY)
        self.assertEqual(rows,[])

    def test_stale_jobs_and_expired_deadlines_stop_counting_active(self):
        self.assertEqual(effective_status({'status':'Open','lastChecked':'2026-10-01'},TODAY),'Pending verification')
        self.assertEqual(effective_status({'status':'Open','lastChecked':'2026-11-02','closingDate':'2026-11-02'},TODAY),'Closed')

    def test_resume_deadline_label_is_supported_without_taking_publication_date(self):
        self.assertEqual(extract_labeled_date('Published October 28, 2026. Deadline for Resumes: Tuesday, November 10, 2026 at 4:30 pm',('deadline',)),'2026-11-10')

    def test_facebook_login_pages_cannot_count_as_successful_job_sources(self):
        meta=source_check_metadata({'id':'f','url':'https://facebook.com/nation','sourceType':'verified_official_facebook'},
                                   {'f':{'url':'https://facebook.com/nation','status':'checked','lastChecked':'2026-11-02'}},TODAY)
        self.assertEqual(meta['checkStatus'],'authorized_api_required');self.assertIsNone(meta['lastChecked'])
        with patch('tools.jobs_collector.public_fetcher') as fetch:
            self.assertIn('authorized platform API',fetch_markup('https://facebook.com/nation')[1]);fetch.assert_not_called()

    def test_posting_permalink_does_not_assign_its_related_jobs_to_the_same_community(self):
        source={'id':'mko','name':'MKO','url':'https://mko.test/job/','parser':'job_detail','jobTitle':'Community Justice Worker',
                'communityIds':['317'],'communityNames':['Northlands Denesuline First Nation'],'verifiedOfficialSource':True}
        html='<h1>Community Justice Worker in Northlands Denesuline First Nation</h1><p>This recruitment is open until filled.</p><a href="/other-job/">Wellness Worker in Another Nation</a>'
        with patch('tools.jobs_collector.fetch_markup',return_value=(html,None)):
            rows,_,_,_=fetch_source(source,TODAY)
        self.assertEqual([(r['title'],r['communityId'],r['sourceUrl']) for r in rows],[('Community Justice Worker','317',source['url'])])
        with patch('tools.jobs_collector.fetch_markup',return_value=(html.replace('Northlands Denesuline First Nation','Another Nation'),None)):
            self.assertEqual(fetch_source(source,TODAY)[0],[])

    def test_verified_closure_withdraws_manual_job_and_offline_refresh_does_not_reopen_it(self):
        source={'id':'s','name':'Nation','url':'https://nation.test/job/','communityIds':['1']}
        original={'id':'manual','title':'Community Worker','employer':'Nation','communityId':'1','sourceId':'s','sourceUrl':source['url'],
                  'status':'Open','lastChecked':'2026-11-02','verifiedOfficialSource':True,'manualOverride':True,'salary':'$70,000'}
        closed={**original,'id':'discovered','manualOverride':False,'status':'Closed','lastChecked':'2026-11-03','extractionConfidence':'high'}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'jobs-overrides.json').write_text(json.dumps({'manualListings':[original]}))
            (root/'jobs-data.json').write_text(json.dumps({'listings':[original]}))
            with patch('tools.jobs_collector.configured_sources',return_value=[source]),patch('tools.jobs_collector.fetch_source',return_value=([closed],[],'Community Worker posting closed',[])):
                data,_=collect(root,TODAY)
                row=next(r for r in data['listings'] if r['manualOverride'])
                self.assertEqual((row['status'],row['salary']),('Closed','$70,000'))
                (root/'jobs-data.json').write_text(json.dumps(data))
                data,_=collect(root,date(2026,11,4),offline=True)
                self.assertEqual(next(r for r in data['listings'] if r['manualOverride'])['status'],'Closed')


class PublicPageTests(unittest.TestCase):
    def test_registered_article_itself_is_ingested_with_publisher_date(self):
        html='<h1>New school for Test Nation</h1><meta property="article:published_time" content="2026-10-22"><meta property="og:title" content="New school for Test Nation"><p>Test Nation announced a new school.</p>'
        c={'bandId':1,'communityName':'Test Nation','provinceTerritory':'MB'}
        row=direct_article_candidate(html,'https://nation.test/news/school',c,{'name':'Nation','type':'Official First Nation Website'})
        self.assertEqual(row['publishedAt'],'2026-10-22');self.assertTrue(row['detailVerified'])
        self.assertIsNone(direct_article_candidate('<script type="application/ld+json">{"@type":"WebSite","datePublished":"2026-10-22"}</script>', 'https://nation.test/',c,{}))

    def test_shared_article_requires_explicit_community_association(self):
        html='<meta property="article:published_time" content="2026-10-22"><meta property="og:title" content="New school for Other Nation">'
        self.assertIsNone(direct_article_candidate(html,'https://publisher.test/news/school',{'bandId':1,'communityName':'Test Nation'}, {'requiresCommunityMention':True}))

    def test_eventer_details_use_visible_dates_location_and_end_date(self):
        html='<h1>Safety Tickets Training</h1><span class="eventer-event-time">November 2, 2026, 12:00 AM to November 7, 2026, 11:59 PM</span><span class="eventer-event-venue">Community Arena</span>'
        row=extract_eventer_detail(html,'https://nation.test/eventer/safety/edate/2026-11-02',{'bandId':1,'communityName':'Test Nation'}, {})
        self.assertEqual((row['startDate'],row['endDate'],row['location']),('2026-11-02','2026-11-07','Community Arena'))
        self.assertTrue(is_publishable_event(row,TODAY))
        self.assertTrue(row['allDay']);self.assertNotIn('startTime',row)

    def test_cancelled_calendar_occurrence_cannot_remain_upcoming(self):
        html='<h1>Cancelled Community Workshop</h1><span class="eventer-event-date">November 4, 2026</span>'
        row=extract_eventer_detail(html,'https://nation.test/eventer/workshop/edate/2026-11-04',{'bandId':1,'communityName':'Test Nation'}, {})
        self.assertEqual(row['eventStatus'],'cancelled');self.assertFalse(is_publishable_event(row,TODAY))

    def test_eventer_url_date_does_not_override_different_visible_date(self):
        html='<h1>Community Workshop</h1><span class="eventer-event-date">November 4, 2026</span>'
        self.assertIsNone(extract_eventer_detail(html,'https://nation.test/eventer/workshop/edate/2026-11-03',{'bandId':1,'communityName':'Test Nation'},{}))


if __name__=='__main__':unittest.main()
