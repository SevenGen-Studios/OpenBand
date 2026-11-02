import unittest
from pathlib import Path
from tools.build_site import provincial_landing

ROOT = Path(__file__).resolve().parents[1]

class ManitobaRoutes(unittest.TestCase):
    def test_generated_route_matches_shared_template(self):
        base = (ROOT / 'index.html').read_text()
        base = base.replace('<a class="logo" href="/">Open<em>Band</em></a>', '<a class="logo" href="/">Open<em>Band</em></a><a class="nav-home" id="homeLink" href="/">Home</a>', 1)
        page = (ROOT / 'manitoba/index.html').read_text()
        self.assertEqual(page, provincial_landing(base, 'MB', 'Manitoba'))
        self.assertIn('data-province="MB"', page)
        self.assertIn('https://openband.ca/manitoba/', page)
        self.assertNotIn('/alberta-coverage-report.html', page)
        self.assertIn('https://openband.ca/manitoba/', (ROOT / 'sitemap.xml').read_text())
