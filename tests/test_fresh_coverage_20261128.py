import gzip,json,unittest
from datetime import date,timedelta
from pathlib import Path
from unittest.mock import patch
from tools.apply_community_enrichment import validate
from tools.community_coverage import inventory
from tools.jobs_collector import fetch_source,effective_status,ACTIVE_STATUSES
from tools.news_discovery import prune_invalid_generated_articles
ROOT=Path(__file__).resolve().parents[1]
FOLDER=ROOT/'research/community-intelligence/fresh-2026-11-28'
TODAY=date(2026,11,28)
class FreshCoverageTests(unittest.TestCase):
    def entries(self):return json.loads((FOLDER/'reviewed-enrichment.json').read_text())['records']
    def test_reviewed_records_have_intact_archived_evidence(self):
        roster={str(b['id']) for b in json.loads((ROOT/'data.json').read_text())['bands']}
        for e in self.entries():
            with self.subTest(id=e['record']['id']):validate(e,roster,{},ROOT,TODAY)
    def test_news_is_recent_and_not_pruned(self):
        for e in self.entries():
            if e['kind']!='news':continue
            r=e['record'];self.assertGreaterEqual(date.fromisoformat(r['publishedAt']),TODAY-timedelta(days=30))
            retained,removed=prune_invalid_generated_articles([r],TODAY);self.assertEqual(retained,[r]);self.assertFalse(removed)
    def test_noon_distribution_time_is_not_assigned_to_meals(self):
        events=[e['record'] for e in self.entries() if e['kind']=='events'];self.assertEqual(len(events),5)
        for row in events:
            self.assertNotIn('startTime',row);self.assertNotIn('endTime',row)
            self.assertGreater(date.fromisoformat(row['startDate']),TODAY)
        self.assertEqual(next(r for r in events if 'Edmonton' in r['location'])['timeZone'],'America/Edmonton')
    def test_employer_scan_reaches_plural_job_titles(self):
        source=next(s for s in json.loads((ROOT/'jobs-sources.json').read_text())['sources'] if s['id']=='research-fisher-river-jobs')
        markup=gzip.decompress((FOLDER/'fisher-jobs.html.gz').read_bytes()).decode()
        with patch('tools.jobs_collector.fetch_markup',return_value=(markup,None)),patch('tools.jobs_collector.inspect_candidate_page',return_value=({},[])) as inspect:
            fetch_source(source,TODAY)
        checked={call.args[0] for call in inspect.call_args_list}
        for e in self.entries():
            if e['kind']=='jobs':self.assertIn(e['record']['sourceUrl'],checked)
    def test_jobs_have_explicit_availability_and_freshness_expiry(self):
        for e in self.entries():
            if e['kind']!='jobs':continue
            row=e['record'];self.assertIn(effective_status(row,TODAY),ACTIVE_STATUSES)
            self.assertNotIn(effective_status(row,TODAY+timedelta(days=22)),ACTIVE_STATUSES)
    def test_two_specific_nations_gain_all_four(self):
        rows={r['communityId']:r for r in inventory(ROOT,TODAY)['communities']}
        self.assertTrue(rows['395']['allFour']);self.assertTrue(rows['264']['allFour'])
    def test_project_update_preserves_historical_status_without_inventing_completion(self):
        update=json.loads((FOLDER/'project-update.json').read_text());before,after=update['before'],update['after']
        self.assertEqual(after['status'],before['status']);self.assertEqual(after['statusAsOf'],before['statusAsOf'])
        self.assertNotIn('completionDate',after);self.assertIn('not a fresh confirmation',after['description'])
        self.assertEqual(update['evidence']['sourcePages'],[1,6]);self.assertEqual(len(update['evidence']['originalDocumentSha256']),64)
