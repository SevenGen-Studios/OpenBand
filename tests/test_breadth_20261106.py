import copy
import json
import unittest
from datetime import date
from tools.events_discovery import extract_html_events, is_publishable_event, merge_events
from tools.jobs_collector import bamboo_embed_candidates

TODAY=date(2026,11,6)
COMMUNITY={'bandId':344,'communityName':'Onion Lake Cree Nation','provinceTerritory':'SK'}
SOURCE={'name':'Onion Lake Cree Nation','type':'Official First Nation Website','status':'verified'}

def calendar(rows, titles=None):
    cards=''.join('<div class="olcn-ev-detail" data-slug="'+r['slug']+'"><h3 class="olcn-evd-title">'+(titles or {}).get(r['slug'],r['t'])+'</h3><div>Published event details</div></div>' for r in rows)
    return '<script type="application/json" id="olcn-ev-data-test">'+json.dumps(rows)+'</script>'+cards

class PublishedCalendarTests(unittest.TestCase):
    def setUp(self):
        self.rows=[{'t':'Community round dance','slug':'first','s':'2026-11-17','e':'2026-11-17','u':'https://onionlake.ca/events/first/'},{'t':'Community round dance','slug':'second','s':'2026-11-24','e':'2026-11-24','u':'https://onionlake.ca/events/second/'}]
    def extract(self, markup, community=COMMUNITY):
        return extract_html_events(markup,'https://onionlake.ca/events/',community,SOURCE,TODAY)[0]
    def test_each_occurrence_keeps_its_own_dates_and_identity(self):
        rows=self.extract(calendar(self.rows))
        self.assertEqual([r['startDate'] for r in rows],['2026-11-17','2026-11-24'])
        self.assertEqual(len({r['id'] for r in rows}),2)
        self.assertTrue(all(is_publishable_event(r,TODAY) for r in rows))
    def test_json_must_match_the_rendered_event_card(self):
        self.assertEqual(self.extract(calendar(self.rows,{'first':'Different title','second':'Different title'})),[])
    def test_foreign_urls_and_reversed_dates_are_rejected(self):
        rows=copy.deepcopy(self.rows);rows[0]['u']='https://unrelated.test/events/first';rows[1]['e']='2026-11-01'
        self.assertEqual(self.extract(calendar(rows)),[])
    def test_wrong_community_cannot_inherit_this_calendar(self):
        rows=self.extract(calendar(self.rows),{**COMMUNITY,'bandId':353,'communityName':'Lac La Ronge Indian Band'})
        self.assertFalse(any(r.get('extractionMethod')=='olcn-calendar' for r in rows))
    def test_repeat_scan_preserves_existing_record_identity(self):
        fresh=self.extract(calendar(self.rows));old={**fresh[0],'id':'existing-public-id','title':'Community round dance November 17, 2026'}
        merged=merge_events([old],fresh,TODAY)
        self.assertEqual(len(merged),2)
        self.assertEqual(next(r['id'] for r in merged if r['startDate']=='2026-11-17'),'existing-public-id')
    def test_published_time_is_not_truncated_by_adjacent_html(self):
        self.rows[0]['tm']='12:30 pm'
        row=self.extract(calendar(self.rows))[0]
        self.assertEqual(row['startTime'],'12:30 PM')
        self.assertNotIn('location',row)
    def test_conflicting_program_dates_are_held(self):
        markup=calendar(self.rows).replace('Published event details','<div class="olcn-evd-body">Program starts November 23, 2026</div>')
        self.assertEqual(self.extract(markup),[])
    def test_malformed_calendar_is_held_without_guessing_dates(self):
        self.assertEqual(self.extract('<script type="application/json" id="olcn-ev-data-test">{broken}</script>'),[])

class PublicEmployerFeedTests(unittest.TestCase):
    def setUp(self):
        self.source={'id':'test','url':'https://fortmckay.bamboohr.com/jobs/embed2.php?format=json','name':'Fort McKay First Nation','communityIds':['467'],'communityNames':['Fort McKay First Nation'],'verifiedOfficialSource':True}
        self.payload={'success':True,'departments':[{'label':'Health','positions':[{'name':'Health Care Aid','url':'https://fortmckay.bamboohr.com/careers/140','location':'Fort McKay, AB'},{'name':'General Expression of Interest','url':'https://fortmckay.bamboohr.com/careers/1'}]}]}
    def test_live_feed_is_a_lead_not_an_invented_deadline(self):
        rows,warnings=bamboo_embed_candidates(json.dumps(self.payload),self.source,TODAY)
        self.assertFalse(warnings);self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['status'],'Pending verification');self.assertIsNone(rows[0]['closingDate'])
    def test_other_employer_urls_are_not_borrowed(self):
        self.payload['departments'][0]['positions'][0]['url']='https://unrelated.test/careers/140'
        self.assertEqual(bamboo_embed_candidates(json.dumps(self.payload),self.source,TODAY)[0],[])
    def test_employer_association_requires_review(self):
        self.assertFalse(bamboo_embed_candidates(json.dumps(self.payload),{**self.source,'verifiedOfficialSource':False},TODAY)[0])

    def test_fetch_source_accepts_json_only_for_the_configured_adapter(self):
        from unittest.mock import patch
        from tools.jobs_collector import fetch_source
        source={**self.source,'parser':'bamboo_embed'}
        with patch('tools.jobs_collector.fetch_binary', return_value=(json.dumps(self.payload).encode(),'application/json',None)), patch('tools.jobs_collector.fetch_markup') as html_fetch:
            rows,warnings,text,review=fetch_source(source,TODAY)
            self.assertEqual(len(rows),1); self.assertFalse(warnings);self.assertTrue(text)
            html_fetch.assert_not_called()
