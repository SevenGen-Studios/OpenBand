import gzip
import json
import unittest
from datetime import date, timedelta
from pathlib import Path
from tools.apply_community_enrichment import validate
from tools.community_coverage import inventory
from tools.news_discovery import article_page_metadata, prune_invalid_generated_articles
from tools.jobs_collector import effective_status, ACTIVE_STATUSES

ROOT=Path(__file__).resolve().parents[1]
FOLDER=ROOT/'research/community-intelligence/current-2026-11-27'
TODAY=date(2026,11,27)

class CurrentCoverageTests(unittest.TestCase):
    def entries(self):
        return json.loads((FOLDER/'reviewed-enrichment.json').read_text())['records']

    def test_every_record_has_archived_evidence_and_recent_dates(self):
        roster={str(r['id']) for r in json.loads((ROOT/'data.json').read_text())['bands']}
        for entry in self.entries():
            with self.subTest(id=entry['record']['id']):
                validate(entry,roster,{},ROOT,TODAY)
                row=entry['record']
                if entry['kind']=='news':
                    self.assertGreaterEqual(date.fromisoformat(row['publishedAt']),TODAY-timedelta(days=30))
                    retained,removed=prune_invalid_generated_articles([row],TODAY)
                    self.assertEqual(retained,[row]);self.assertFalse(removed)
                elif entry['kind']=='events':
                    self.assertGreater(date.fromisoformat(row['startDate']),TODAY)

    def test_visible_dates_are_scoped_to_reviewed_article_templates(self):
        for filename,url,expected in [
            ('mistawasis-sessions.html.gz','https://mistawasis.ca/community-information-sessions/','2026-11-20'),
            ('ochapowace-dividend.html.gz','https://ochapowace.com/news/kakisiwew-ochapowace-2026-christmas-dividend-form','2026-11-26')]:
            markup=gzip.decompress((FOLDER/filename).read_bytes()).decode()
            self.assertEqual(article_page_metadata(markup,url)['published'],expected)
            self.assertIsNone(article_page_metadata(markup,url.replace('mistawasis.ca','example.test').replace('ochapowace.com','example.test'))['published'])
            markup=markup.replace('class="published"','class="updated"').replace('class="post-date"','class="updated"')
            self.assertIsNone(article_page_metadata(markup,url)['published'])
        stray='<h1>Community Information Sessions</h1><aside><span class="published">Nov 20, 2026</span></aside>'
        self.assertIsNone(article_page_metadata(stray,'https://mistawasis.ca/notices/')['published'])

    def test_jobs_correct_existing_records_without_duplicates_and_expire(self):
        jobs=json.loads((ROOT/'jobs-data.json').read_text())['listings']
        overrides=json.loads((ROOT/'jobs-overrides.json').read_text())
        for e in self.entries():
            if e['kind']!='jobs':continue
            row=e['record'];self.assertEqual(sum(r['id']==row['id'] for r in jobs),1)
            self.assertTrue(any(r['id']==row['id'] for r in overrides['manualListings']))
            self.assertNotIn(row['id'],overrides['corrections'])
            self.assertIn(effective_status(row,TODAY),ACTIVE_STATUSES)
            self.assertNotIn(effective_status(row,TODAY+timedelta(days=22)),ACTIVE_STATUSES)

    def test_dated_capital_update_does_not_invent_construction_status(self):
        projects=[e['record'] for e in self.entries() if e['kind']=='projects']
        self.assertEqual(len(projects),3)
        for row in projects:
            self.assertNotIn('status',row)
            self.assertNotIn('completionDate',row)
            self.assertEqual(row['sources'][0]['datePrecision'],'month')
            self.assertIn('does not establish',row['description'])

    def test_upcoming_events_close_two_specific_all_four_gaps(self):
        rows={r['communityId']:r for r in inventory(ROOT,TODAY)['communities']}
        for key,count in [('374',5),('293',1)]:
            self.assertEqual(rows[key]['upcomingEvents'],count)
            self.assertTrue(rows[key]['allFour'])
