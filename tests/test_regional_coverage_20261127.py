import json
import unittest
from datetime import date,timedelta
from pathlib import Path
from tools.apply_community_enrichment import validate
from tools.community_coverage import inventory
from tools.jobs_collector import effective_status,ACTIVE_STATUSES,listing_is_confirmed_on_source
from tools.news_discovery import prune_invalid_generated_articles
ROOT=Path(__file__).resolve().parents[1]
FOLDER=ROOT/'research/community-intelligence/regional-2026-11-27'
TODAY=date(2026,11,27)

class RegionalCoverageTests(unittest.TestCase):
    def entries(self):
        return json.loads((FOLDER/'reviewed-enrichment.json').read_text())['records']

    def test_all_reviewed_records_have_source_evidence(self):
        roster={str(b['id']) for b in json.loads((ROOT/'data.json').read_text())['bands']}
        for e in self.entries():
            with self.subTest(id=e['record']['id']):validate(e,roster,{},ROOT,TODAY)

    def test_recent_news_and_upcoming_events_survive_publication(self):
        for e in self.entries():
            r=e['record']
            if e['kind']=='news':
                self.assertGreaterEqual(date.fromisoformat(r['publishedAt']),TODAY-timedelta(days=30))
                retained,removed=prune_invalid_generated_articles([r],TODAY)
                self.assertEqual(retained,[r]);self.assertFalse(removed)
            elif e['kind']=='events':
                self.assertGreater(date.fromisoformat(r['startDate']),TODAY)
        edmonton=next(e['record'] for e in self.entries() if e['kind']=='events' and 'Edmonton' in e['record']['location'])
        self.assertEqual(edmonton['timeZone'],'America/Edmonton')
        self.assertNotIn('endTime',edmonton)

    def test_onion_jobs_are_explicitly_open_and_require_rechecks(self):
        config=json.loads((ROOT/'jobs-sources.json').read_text())['sources']
        for e in self.entries():
            if e['kind']!='jobs':continue
            r=e['record'];self.assertIn(effective_status(r,TODAY),ACTIVE_STATUSES)
            self.assertNotIn(effective_status(r,TODAY+timedelta(days=22)),ACTIVE_STATUSES)
            self.assertTrue(any(s['id']==r['sourceId'] and s['verifiedOfficialSource'] for s in config))
            self.assertFalse(listing_is_confirmed_on_source(r,{r['sourceId']:r['title']+' no confirmed opening'}))

    def test_onion_all_four_and_sweetgrass_event_gap(self):
        rows={r['communityId']:r for r in inventory(ROOT,TODAY)['communities']}
        self.assertTrue(rows['344']['allFour'])
        self.assertEqual(rows['348']['upcomingEvents'],4)
        self.assertGreater(rows['394']['recentNews30'],0)

    def test_groundbreaking_does_not_imply_completion(self):
        row=next(e['record'] for e in self.entries() if e['kind']=='projects')
        self.assertEqual(row['groundbreakingDate'],'2026-11-10')
        self.assertNotIn('completionDate',row)
        self.assertNotIn('status',row)
        self.assertIn('does not establish completion',row['description'])
