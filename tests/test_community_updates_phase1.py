"""Synthetic parser fixtures are isolated from published community datasets."""
import copy
import json
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch
from tools import news_discovery as news, events_discovery as events
from tools.community_updates import association_allowed, calendar_url, error_status, feed_links, page_diagnostic, track_changes, quality_metrics, merge_update_reviews


class CommunityUpdatesPhase1Tests(unittest.TestCase):
    def setUp(self):
        self.community={'bandId':295,'communityName':'Dakota Tipi','aliases':['Dakota Tipi First Nation'],'provinceTerritory':'MB'}
        self.source={'type':'Official First Nation Website','name':'Dakota Tipi','url':'https://community.example/','official':True,'adapter':'html','status':'verified'}
        self.today=date(2026,11,2)

    def test_every_identity_and_province_survives_registry_integration(self):
        data=news.load_json(news.DATA_PATH,{});rows=news.ensure_registry(data,{},{} )['communities']
        self.assertEqual(len(rows),180)
        self.assertEqual({str(r['bandId']) for r in rows},{str(b['id']) for b in data['bands']})
        for province,count in [('SK',69),('AB',48),('MB',63)]:self.assertEqual(sum(r['provinceTerritory']==province for r in rows),count)
        self.assertTrue(all('Manitoba' in ' '.join(r['discoveryQueries']) for r in rows if r['provinceTerritory']=='MB'))

    def test_contact_registration_is_not_working_source_verification(self):
        with patch.object(news,'load_json',side_effect=lambda path,default: {'contacts':[{'nation_id':999,'website_url':'https://community.example'}]} if path==news.CONTACTS_PATH else default):
            row=news.ensure_registry({'bands':[{'id':999,'name':'Example Nation','province':'MB'}]}, {},{})['communities'][0]
        source=next(s for s in row['sources'] if s['adapter']=='html')
        self.assertEqual(source['status'],'candidate')

    def test_title_category_beats_unrelated_health_chrome(self):
        self.assertEqual(news.classify_category('Halloween with our Elders','Healthcare department clinic services'), 'Community Events')
        self.assertEqual(news.classify_category('Housing application update','Healthcare department'),'Housing')
        self.assertEqual(news.classify_category('Emergency evacuation notice','Health and wellness'),'Emergencies')
        self.assertEqual(events.event_category('Voter registration clinic','Wellness department'),'Governance & Meetings')

    def test_calendar_query_date_is_not_publication(self):
        self.assertTrue(calendar_url('https://community.example/events.html?EventID=754'))
        meta=news.article_page_metadata('<h1>Halloween gathering</h1><time datetime="2026-10-31">October 31</time>', 'https://community.example/events.html?EventID=754')
        self.assertIsNone(meta['published'])
        explicit=news.article_page_metadata('<meta property="article:published_time" content="2026-10-20"><time datetime="2026-10-31">Event</time>', 'https://community.example/events.html?EventID=754')
        self.assertEqual(explicit['published'],'2026-10-20')

    def test_modified_time_and_atom_updated_do_not_become_publication(self):
        self.assertIsNone(news.article_page_metadata('<h1>Housing update</h1><time class="updated" datetime="2026-10-30"></time>','https://community.example/housing')['published'])
        feed=b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Housing update</title><updated>2026-10-30</updated><link href="https://community.example/housing"/></entry></feed>'
        self.assertEqual(news.extract_feed_candidates(feed,'https://community.example/feed',self.community,self.source),[])

    def test_feed_discovery_is_explicit_same_host_and_deduplicated(self):
        markup='<link rel="alternate" type="application/rss+xml" href="/feed/"><link rel="alternate" type="application/rss+xml" href="https://evil.example/feed/"><link rel="alternate" type="application/rss+xml" href="/feed/">'
        self.assertEqual(feed_links(markup,self.source['url']),['https://community.example/feed/'])

    def test_shared_source_requires_local_community_evidence(self):
        source={**self.source,'requiresCommunityMention':True,'associationCommunityNames':['Dakota Tipi','Birdtail Sioux']}
        self.assertFalse(association_allowed(self.community,source,'Birdtail Sioux community meeting','Local gathering'))
        self.assertTrue(association_allowed(self.community,source,'Dakota Tipi and Birdtail Sioux gathering','Two Nations participating'))
        self.assertFalse(association_allowed(self.community,source,'Community meeting','Dakota Tipi Birdtail Sioux council footer'))

    def test_diagnostics_distinguish_javascript_domain_and_tls(self):
        self.assertEqual(page_diagnostic('<title>SDY Lotto</title>','https://community.example',self.community,self.source),'unrelated_or_parked_domain')
        self.assertEqual(page_diagnostic('<div id="root"></div><script type="module" src="app.js"></script>','https://community.example',self.community,self.source),'javascript_required')
        self.assertEqual(error_status(Exception('SSL certificate has expired')),'tls_error')
        self.assertEqual(error_status(PermissionError('robots.txt disallows URL')),'robots_blocked')
        self.assertEqual(error_status(PermissionError('robots.txt unavailable (503)')),'robots_unavailable')

    def test_news_permalink_edit_retains_id_and_first_seen(self):
        old={'id':'stable','bandId':295,'title':'Housing notice','url':'https://community.example/housing','publishedAt':'2026-10-20','summary':'Original source text','sourceType':'Official First Nation Website','discoveredAt':'2026-10-21T00:00:00Z'}
        revised={**old,'id':'different-parser-id','summary':'Corrected source text','discoveredAt':'2026-11-02T00:00:00Z'}
        merged,added=news.merge_articles([old],[revised]);self.assertEqual(added,[]);self.assertEqual(merged[0]['id'],'stable');self.assertEqual(merged[0]['discoveredAt'],old['discoveredAt']);self.assertEqual(merged[0]['summary'],revised['summary'])
        changes=track_changes([old],merged,'2026-11-02T00:00:00Z');self.assertEqual(changes[0]['change'],'updated')
        self.assertEqual(track_changes(copy.deepcopy(merged),copy.deepcopy(merged),'2026-11-03T00:00:00Z'),[])

    def test_same_title_different_number_or_community_is_not_deduplicated(self):
        a={'id':'one','bandId':295,'title':'Community meeting November 3','publishedAt':'2026-11-01','url':'https://community.example/one'}
        b={**a,'id':'two','title':'Community meeting November 4','url':'https://community.example/two'}
        c={**a,'id':'three','bandId':284}
        self.assertEqual(len(news.merge_articles([a],[b,c])[0]),3)

    def test_jsonld_keeps_publication_event_date_time_and_address_independent(self):
        payload={'@type':'Event','@id':'event-42','name':'Community Cultural Evening','startDate':'2026-11-10T18:30:00-06:00','endDate':'2026-11-10T21:00:00-06:00','datePublished':'2026-10-21','location':{'name':'Community Hall','address':{'streetAddress':'12 Main Street','addressLocality':'Dakota Tipi'}},'url':'/cultural-evening'}
        p=events.EventPageParser();p.feed('<script type="application/ld+json">'+json.dumps(payload)+'</script>')
        row=events.extract_jsonld_events(p,'https://community.example/',self.community,self.source)[0]
        self.assertEqual(row['startDate'],'2026-11-10');self.assertEqual(row['publishedAt'],'2026-10-21');self.assertEqual(row['startTime'],'18:30');self.assertEqual(row['endTime'],'21:00');self.assertEqual(row['startTimeOffset'],'-06:00');self.assertIn('12 Main Street',row['location'])

    def test_icalendar_all_day_end_is_exclusive_and_recurrence_is_reviewed(self):
        payload=b'BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:annual\nSUMMARY:Community Feast\nDTSTART;VALUE=DATE:20261110\nDTEND;VALUE=DATE:20261112\nLOCATION:Community Hall\nURL:https://community.example/feast\nEND:VEVENT\nBEGIN:VEVENT\nUID:weekly\nSUMMARY:Weekly Meeting\nDTSTART:20261110T190000\nRRULE:FREQ=WEEKLY\nEND:VEVENT\nEND:VCALENDAR'
        rows,review=events.extract_ical_events(payload,'https://community.example/calendar.ics',self.community,self.source)
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['endDate'],'2026-11-11');self.assertNotIn('startTime',rows[0]);self.assertEqual(len(review),1)

    def test_same_day_same_category_distinct_events_remain_separate(self):
        base={'bandId':295,'startDate':'2026-11-10','description':'Event date: November 10, 2026','category':'Community Event','extractionMethod':'shared-index','confidence':.95}
        rows=events.merge_events([],[{**base,'id':'a','title':'Community Feast','sourceUrl':'https://community.example/feast'},{**base,'id':'b','title':'Community Gathering','sourceUrl':'https://community.example/gathering'}],self.today)
        self.assertEqual(len(rows),2)

    def test_cancellation_withdraws_existing_schedule_and_reschedule_retains_uid_id(self):
        old={'id':'stable','bandId':295,'title':'Community Feast','startDate':'2026-11-10','sourceUrl':'https://community.example/feast','sourceUid':'uid-1','extractionMethod':'json-ld','confidence':.98}
        revised={**old,'id':'new','startDate':'2026-11-12'}
        merged=events.merge_events([old],[revised],self.today);self.assertEqual(merged[0]['id'],'stable');self.assertEqual(merged[0]['startDate'],'2026-11-12')
        self.assertEqual(events.merge_events([old],[dict(old,eventStatus='cancelled')],self.today),[])

    def test_yearless_ocr_is_not_published_as_guessed_event(self):
        row={'id':'x','title':'Community Feast','bandId':295,'startDate':'2026-11-10','description':'Community Feast November 10','sourceUrl':'https://community.example/poster.png','extractionMethod':'ocr-image','confidence':.98}
        self.assertFalse(events.is_publishable_event(row,self.today))

    def test_quality_does_not_count_unscanned_or_authenticated_sources_as_working(self):
        registry={'communities':[self.community,dict(self.community,bandId=284,communityName='Birdtail Sioux')]}
        runs=[{'bandId':295,'status':'authorized_api_required','pagesChecked':0}]
        quality=quality_metrics(registry,[],runs,[],self.today)
        self.assertEqual(quality['byProvince']['MB']['communitiesTracked'],2)
        self.assertEqual(quality['byProvince']['MB']['communitiesWithWorkingSourcesThisRun'],0)
        self.assertEqual(quality['communities'][1]['discoveryState'],'not_scanned')

    def test_failed_source_retains_previously_valid_articles(self):
        old={'id':'valid','title':'Housing funding announcement','bandId':295,'publishedAt':'2026-10-20','url':'https://community.example/housing','dateSource':'article:published_time'}
        retained,removed=news.prune_invalid_generated_articles([old],self.today)
        self.assertEqual(news.merge_articles(retained,[])[0],[old]);self.assertEqual(removed,[])

    def test_review_repeated_scan_keeps_one_finding_and_first_seen(self):
        old={'bandId':295,'url':'https://community.example','status':'timeout','reason':'Source timed out','firstSeenAt':'2026-10-01'}
        merged=merge_update_reviews([old],[{**old,'discoveredAt':'2026-11-02'}],'2026-11-02')
        self.assertEqual(len(merged),1);self.assertEqual(merged[0]['firstSeenAt'],'2026-10-01')


class FeedPublisherSafetyTests(unittest.TestCase):
    def test_comment_feed_and_term_employment_are_not_news(self):
        c={'bandId':309,'communityName':'Chemawawin Cree Nation'};s={'official':True,'type':'Official First Nation Website'}
        feed=b'<rss><channel><title>Comments for Council</title><item><title>Comment on One Time Multiple Day Event by casino in Uitgeest</title><link>https://example.test/event</link><pubDate>Mon, 02 Nov 2026 10:00:00 GMT</pubDate><description>Community event meeting update.</description></item></channel></rss>'
        self.assertEqual(news.extract_feed_candidates(feed,'https://example.test/comments/feed',c,s),[])
        self.assertTrue(news.employment_item('Recreation Assistant (Sports & Recreation) - Term Opportunity'))
        self.assertTrue(news.employment_item('Primary Care Registered Nurse - Full Time Opportunity'))
        self.assertEqual(feed_links('<link rel="alternate" type="application/rss+xml" title="Comments Feed" href="/comments/feed/">','https://example.test'),[])

class EventCardDateSafetyTests(unittest.TestCase):
    def test_card_publication_date_cannot_replace_yearless_event_date(self):
        start,end=events.choose_event_date('Community Trust Member Meeting - November 4','Published October 22, 2026',date(2026,11,2))
        self.assertNotEqual(start,'2026-10-22')
        self.assertFalse(events.is_publishable_event({'title':'Member Meeting - November 4','startDate':start,'description':'Published October 22, 2026','sourceUrl':'https://example.test/meeting','extractionMethod':'html'},date(2026,11,2)))
        start,end=events.choose_event_date('Member Meeting - November 4','Event date: November 4, 2026. Published October 22, 2026',date(2026,11,2))
        self.assertEqual(start,'2026-11-04')

    def test_iso_publication_date_is_excluded_from_event_dates(self):
        self.assertEqual(events.choose_event_date('Community Feast','Published: 2026-10-20. Event date: 2026-11-10',date(2026,11,2))[0],'2026-11-10')

    def test_explicit_full_date_and_cross_year_ranges_keep_end_date(self):
        self.assertEqual(events.choose_event_date('Powwow Nov 7, 2026 - Nov 8, 2026','',date(2026,11,2)),('2026-11-07','2026-11-08'))
        self.assertEqual(events.explicit_written_ranges('Gathering December 31 - January 2, 2027'),[('2026-12-31','2027-01-02')])

class RecordedCardRegressionTests(unittest.TestCase):
    def test_fisher_river_publication_icon_cannot_set_meeting_date(self):
        text='insert_link Community Trust Community Trust Off-Reserve Member Meeting – November 4 today October 22, 2026 41'
        record={'title':text,'description':text,'startDate':'2026-10-22','sourceUrl':'https://fisherriver.ca/2026/10/community-trust-off-reserve-member-meeting-november-4','extractionMethod':'html'}
        self.assertFalse(events.is_publishable_event(record,date(2026,11,2)))


class DiscoveryPublicationTests(unittest.TestCase):
    def test_gdelt_seen_date_is_review_only_until_publisher_verified(self):
        class Fetcher:
            def get(self,url,headers=None):
                return json.dumps({'articles':[{'title':'Dakota Tipi housing program update','url':'https://example.test/housing','seendate':'20261102T130000Z'}]}).encode(),url,'application/json'
        rows=news.discover_gdelt_articles(Fetcher(),{'bandId':295,'communityName':'Dakota Tipi','provinceTerritory':'MB'})
        self.assertIsNone(rows[0]['publishedAt'])
        self.assertEqual(rows[0]['dateSource'],'discovery-index')
        self.assertIn('publication date',news.candidate_review_reason(rows[0],date(2026,11,2),.82))

    def test_mismatched_detail_page_cannot_verify_a_listing_date(self):
        class Fetcher:
            def get(self,url):
                return b'<meta property="article:published_time" content="2026-11-02"><h1>Unrelated school closure</h1>',url,'text/html'
        item={'url':'https://example.test/housing','title':'Housing program update','dateSource':'structured-listing','publishedAt':'2026-11-02'}
        result,warning=news.enrich_html_candidate(Fetcher(),item)
        self.assertFalse(result.get('detailVerified'));self.assertIn('title',warning)



class Phase1FrontendCompatibilityTests(unittest.TestCase):
    def test_authoritative_ids_routes_and_source_states_in_browser_logic(self):
        import shutil,subprocess
        node=shutil.which('node')
        if not node:self.skipTest('Node.js required for frontend compatibility tests')
        result=subprocess.run([node,'tests/test_community_updates_runtime.js'],cwd=news.ROOT,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_successful_http_challenge_is_not_a_working_source(self):
        self.assertEqual(page_diagnostic('<title>Just a moment...</title><h1>Checking your browser</h1>','https://example.test',{},{}),'access_restricted')



class EmploymentEventSeparationTests(unittest.TestCase):
    def test_clinic_job_is_not_a_community_clinic_event(self):
        self.assertFalse(events.is_event_text('Primary Care Registered Nurse (Clinic) - Full Time Opportunity','Applications close November 10, 2026'))
        self.assertTrue(events.is_event_text('Community Career Fair','Event date November 10, 2026'))



class ProvincialPilotTests(unittest.TestCase):
    def test_manitoba_pilot_uses_local_communities_without_integer_id_assumptions(self):
        import contextlib,io
        with patch('sys.argv',['news_discovery','--province','mb','--pilot','--dry-run','--skip-search']):args=news.parse_args()
        with patch.object(news,'scan_source',return_value=([],[],[],['https://fixture.example'])),contextlib.redirect_stdout(io.StringIO()):
            report=news.run(args)
        self.assertEqual(set(report['scanScope']['communityIds']),{str(v) for v in news.PROVINCIAL_PILOTS['MB']})
        self.assertFalse(report['scanScope']['fullScan'])


if __name__=='__main__':unittest.main()
