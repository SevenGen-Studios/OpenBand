import unittest
from pathlib import Path
from tools.build_site import provincial_landing
from tools.seo_records import PROVINCES, province_path

ROOT = Path(__file__).resolve().parents[1]

class BritishColumbiaRoutes(unittest.TestCase):
    def test_shared_template_and_canonical_route(self):
        base = (ROOT / 'index.html').read_text(encoding='utf-8')
        bands=__import__('json').loads((ROOT/'data.json').read_text(encoding='utf-8'))['bands']
        page = provincial_landing(base, 'BC', PROVINCES['BC'],bands)
        self.assertEqual(province_path(PROVINCES['BC']), '/british-columbia/')
        self.assertEqual(page, (ROOT / 'british-columbia/index.html').read_text(encoding='utf-8'))
        for text in ('data-page="province" data-province="BC"', 'https://openband.ca/british-columbia/', '<h1 id="heroTitle">British Columbia First Nations</h1>', 'href="/browse/?province=BC"', 'British Columbia community profiles are available.', 'Not yet indexed', 'dated governance information'):
            self.assertIn(text, page)
        self.assertNotIn('/british columbia/', page)
        self.assertNotIn('/alberta-coverage-report.html', page)
        self.assertIn('https://openband.ca/british-columbia/', (ROOT / 'sitemap.xml').read_text(encoding='utf-8'))
