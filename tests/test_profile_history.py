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
        cls.bands = json.loads((ROOT / 'data.json').read_text(encoding='utf-8'))['bands']

    def test_every_published_nation_has_one_history(self):
        self.assertEqual(len(self.records), len(self.bands))
        self.assertEqual({r['profile_id'] for r in self.records}, {str(b['id']) for b in self.bands})
        pages = list((ROOT / 'first-nations').glob('*/index.html'))
        history_pages = [p.parent.name for p in pages if 'class="history-card"' in p.read_text(encoding='utf-8')]
        self.assertEqual(set(history_pages), {slugify(b['name']) for b in self.bands})

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
        generated = (ROOT / 'assets/profile-history.js').read_text(encoding='utf-8').split('window.OPENBAND_HISTORY=', 1)[1].split(';\n', 1)[0]
        self.assertEqual(json.loads(generated), {r['profile_id']: render_history(r, self.bands, slugify) for r in self.records})
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
        for band in [b for b in self.bands if str(b['id']) in {'400', '403', '398'}]:
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

    def test_every_profile_loads_one_history_asset_and_its_own_markup(self):
        records = {r['profile_id']: r for r in self.records}
        for band in self.bands:
            page = ROOT / 'first-nations' / slugify(band['name']) / 'index.html'
            markup = page.read_text(encoding='utf-8')
            self.assertEqual(markup.count('/assets/profile-history.js?'), 1, str(page))
            self.assertEqual(markup.count('class="history-card"'), 1, str(page))
            self.assertIn(render_history(records[str(band['id'])], self.bands, slugify), markup)

    def test_all_citations_and_connections_are_valid(self):
        profiles = {str(b['id']): b for b in self.bands}
        for record in self.records:
            self.assertEqual(record['band_number'], str(profiles[record['profile_id']]['iscBandNumber']))
            sources = {s['id']: s for s in record['historical_sources']}
            rows = record['historical_overview'] + record.get('key_facts', []) + record['research_notes'] + record['historical_connections'] + record['significant_historical_events']
            for row in rows:
                for source_id in row['source_ids']:
                    self.assertIn(source_id, sources)
                    self.assertTrue(sources[source_id]['url'].startswith('https://'))
                    self.assertEqual(sources[source_id]['verification_status'], 'checked')
            for connection in record['historical_connections']:
                if connection.get('target_profile_id'):
                    self.assertIn(connection['target_profile_id'], profiles)
            markup = render_history(record, self.bands, slugify)
            self.assertIn('Sources Verified', markup)
            self.assertNotIn('View Sources', markup)
            self.assertNotIn('Historical Connections', markup.split('<details', 1)[0])
            self.assertNotIn('<details class="history-more" open', markup)
            self.assertEqual('Historical Connections' in markup, bool(record['historical_connections']))

    def test_duplicate_isc_number_has_distinct_histories(self):
        records = {r['profile_id']: r for r in self.records}
        self.assertEqual(records['462']['band_number'], records['ab-whitefish-lake-128']['band_number'])
        self.assertNotEqual(records['462']['historical_overview'], records['ab-whitefish-lake-128']['historical_overview'])

    def test_no_profile_has_a_source_panel(self):
        for page in (ROOT / 'first-nations').glob('*/index.html'):
            markup = page.read_text(encoding='utf-8')
            self.assertNotIn('View Sources', markup)


if __name__ == '__main__':
    unittest.main()
