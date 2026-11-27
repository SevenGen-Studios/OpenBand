import gzip
import json
import unittest
from datetime import date
from pathlib import Path
from tools.apply_community_enrichment import validate
from tools.news_discovery import article_page_metadata, prune_invalid_generated_articles
from tools.events_discovery import is_publishable_event
from tools.jobs_collector import normalize_listing, effective_status

ROOT=Path(__file__).resolve().parents[1]
FOLDER=ROOT/'research/community-intelligence/breadth-2026-11-27'

class BreadthNovember27Tests(unittest.TestCase):
    def test_source_backed_batch_and_scheduled_retention(self):
        roster={str(b['id']) for b in json.loads((ROOT/'data.json').read_text())['bands']}
        entries=json.loads((FOLDER/'reviewed-enrichment.json').read_text())['records']
        for entry in entries:
            validate(entry,roster,{},ROOT,date(2026,11,27))
            row=entry['record']
            if entry['kind']=='news':
                kept,removed=prune_invalid_generated_articles([row],date(2026,11,27))
                self.assertEqual(kept,[row]);self.assertFalse(removed)
            if entry['kind']=='events':
                self.assertTrue(is_publishable_event(row,date(2026,11,27)))
            if entry['kind']=='jobs':
                normalized=normalize_listing(row,date(2026,11,27))
                self.assertIn(effective_status(normalized,date(2026,11,27)),{'Open','Closing soon'})
                self.assertEqual(effective_status(normalized,date(2026,12,1)),'Closed')

    def test_saskpower_release_date_is_scoped_to_article_heading(self):
        markup=gzip.decompress((FOLDER/'canoe-wind.html.gz').read_bytes()).decode()
        url='https://www.saskpower.com/about-us/media-information/news-releases/2026/construction-on-200-mw-rose-valley-wind-project-now-underway'
        self.assertEqual(article_page_metadata(markup,url)['published'],'2026-06-15')
        self.assertIsNone(article_page_metadata(markup,'https://example.test/news-releases/story')['published'])
        without=markup.replace('class="blog-feature-date"','class="unrelated-date"')
        self.assertIsNone(article_page_metadata(without,url)['published'])

    def test_dinners_are_separate_occurrences_and_membership_is_explicit(self):
        entries=json.loads((FOLDER/'reviewed-enrichment.json').read_text())['records']
        dinners=[e['record'] for e in entries if e['record']['id'].startswith('svdn-christmas')]
        self.assertEqual({r['startDate'] for r in dinners},{'2026-12-12','2026-12-16'})
        self.assertTrue(all(r['startDate']==r['endDate'] for r in dinners))
        canoe=next(e for e in entries if e['record']['id']=='mltc-rose-valley-construction-394-20260615')
        self.assertEqual(len(canoe['evidence']),2)
        self.assertEqual(canoe['record']['associationScope'],'tribal-council-partnership')
