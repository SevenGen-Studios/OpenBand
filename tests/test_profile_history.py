import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.profile_history import render_history
from tools.build_site import slugify


class ProfileHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = json.loads((ROOT / 'history-data.json').read_text(encoding='utf-8'))['records']
        cls.record = cls.records[0]
        cls.bands = [{'id': '400', 'name': 'English River Dene Nation'},
                     {'id': '403', 'name': 'Birch Narrows Dene Nation'},
                     {'id': '398', 'name': 'Buffalo River Dene Nation'}]

    def test_only_canoe_lake_is_published(self):
        self.assertEqual([r['band_number'] for r in self.records], ['394'])
        pages = list((ROOT / 'first-nations').glob('*/index.html'))
        history_pages = [p.parent.name for p in pages if 'class="history-card"' in p.read_text(encoding='utf-8')]
        self.assertEqual(history_pages, ['canoe-lake-cree-first-nation'])

    def test_summary_and_citations(self):
        words = ' '.join(p['text'] for p in self.record['historical_overview']).split()
        self.assertTrue(100 <= len(words) <= 150, len(words))
        source_ids = {s['id'] for s in self.record['historical_sources']}
        for row in self.record['historical_overview'] + self.record['significant_historical_events'] + self.record['historical_connections']:
            self.assertTrue(set(row['source_ids']) <= source_ids)
        markup = render_history(self.record, self.bands, slugify)
        self.assertIn('Sources Verified', markup)
        self.assertNotIn('View Sources', markup)
        self.assertIn('Île-à-la-Crosse, Saskatchewan', markup)
        self.assertIn('A later OTC account lists Canoe Lake', markup)

    def test_badge_requires_checked_citations(self):
        for mutation in ['record', 'source', 'date']:
            record = copy.deepcopy(self.record)
            if mutation == 'record':
                record['verification_status'] = 'pending'
            elif mutation == 'source':
                record['historical_sources'][0]['verification_status'] = 'pending'
            else:
                record['historical_sources'][0]['last_checked_date'] = None
            self.assertNotIn('Sources Verified', render_history(record, self.bands, slugify))

    def test_live_and_static_views_share_markup(self):
        markup = render_history(self.record, self.bands, slugify)
        generated = (ROOT / 'assets/profile-history.js').read_text(encoding='utf-8').split('window.OPENBAND_HISTORY=', 1)[1].strip().removesuffix(';')
        self.assertEqual(json.loads(generated), {'394': markup})
        page = (ROOT / 'first-nations/canoe-lake-cree-first-nation/index.html').read_text(encoding='utf-8')
        self.assertIn(markup, page)
        self.assertRegex(page, r'Elections &amp; Leadership[\s\S]*?</section><section class="history-card"')
        self.assertIn('<summary>Read More', markup)
        self.assertNotIn('history-sources', markup)
        expanded_content = markup.split('<details class="history-more">', 1)[1].split('</details>', 1)[0]
        self.assertIn('Historical Connections', expanded_content)
        self.assertNotIn('<details class="history-more" open', markup)

    def test_related_profiles_and_historical_band(self):
        markup = render_history(self.record, self.bands, slugify)
        for band in self.bands:
            self.assertTrue((ROOT / 'first-nations' / slugify(band['name']) / 'index.html').is_file())
            self.assertIn(f'href="/first-nations/{slugify(band["name"])}/"', markup)
        self.assertIn('Clear Lake Band <span>Historical band', markup)
        self.assertIn('shared_historical_treaty_relationship', json.dumps(self.record))

    def test_content_is_escaped(self):
        record = copy.deepcopy(self.record)
        record['historical_overview'][0]['text'] = '<script>alert("test")</script>'
        markup = render_history(record, self.bands, slugify)
        self.assertNotIn('<script>', markup)
        self.assertIn('&lt;script&gt;', markup)

    def test_only_canoe_lake_loads_history_asset_in_static_pages(self):
        for page in (ROOT / 'first-nations').glob('*/index.html'):
            markup = page.read_text(encoding='utf-8')
            self.assertEqual('/assets/profile-history.js?' in markup,
                             page.parent.name == 'canoe-lake-cree-first-nation', str(page))


if __name__ == '__main__':
    unittest.main()
