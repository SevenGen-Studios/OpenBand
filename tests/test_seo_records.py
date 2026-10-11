import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlsplit
from lxml import html
from tools.seo_records import financial_years, money, publish, annual_page, travel_expenses
from tools.build_site import ROOT, ORIGIN, slugify

class SeoRecordsTests(unittest.TestCase):
    def setUp(self):
        self.band = {'id': 1, 'name': 'Test First Nation', 'province': 'SK', 'filings': [
            {'year': '2023-2024', 'docType': 'Schedule of Remuneration and Expenses', 'posted': True,
             'href': 'https://example.com/source.pdf', 'parse_status': 'parsed', 'people': [{'name': 'Test Official', 'remuneration': 0, 'expenses': None}]}]}
        self.capital = {'bands': {'1': {'years': {'2023-2024': {'parseStatus': 'parsed', 'publishable': True, 'totalRevenue': 100, 'sourceUrl': 'https://example.com/financials.pdf'}}}}}

    def test_review_and_missing_records_do_not_create_pages(self):
        self.band['filings'][0]['manual_review_required'] = True
        self.capital['bands']['1']['years']['2023-2024']['publishable'] = False
        self.assertEqual(financial_years(self.band, self.capital), {})
        self.assertEqual(money(None), 'Not reported')
        self.assertEqual(money(0), '$0')
        self.assertEqual(money(-100), '−$100')

    def test_manual_review_low_confidence_and_unsafe_sources_excluded(self):
        for changes in [{'parse_status': 'manual_review_required'}, {'parse_confidence': 'low'}, {'href': 'javascript:alert(1)'}, {'posted': False}]:
            filing = {**self.band['filings'][0], **changes}
            band = {**self.band, 'filings': [filing]}
            self.assertEqual(financial_years(band, {'bands': {}}), {})

    def test_annual_page_preserves_missing_and_zero_with_original_sources(self):
        years = financial_years(self.band, self.capital)
        page = annual_page(self.band, '2023-2024', years['2023-2024'], years, slugify)
        doc = html.fromstring(page)
        self.assertEqual(len(doc.xpath('//h1')), 1)
        self.assertIn('$0', doc.text_content())
        self.assertIn('Not reported', doc.text_content())
        self.assertIn('https://example.com/source.pdf', doc.xpath('//a/@href'))
        schemas = json.loads(doc.xpath('//script[@type="application/ld+json"]/text()')[0])['@graph']
        dataset = next(x for x in schemas if x['@type'] == 'Dataset')
        self.assertEqual(dataset['temporalCoverage'], '2023/2024')
        self.assertNotIn('license', dataset)
        self.assertIn('https://example.com/financials.pdf', dataset['isBasedOn'])

    def test_canonical_expenses_coalesce_null_without_double_counting(self):
        person = {'name': 'Test Official', 'travel': None, 'expenses': 125925,
                  'creditCard': 136245, 'travelExpenses': 262170, 'otherPayments': None, 'other': 0}
        self.assertEqual(travel_expenses(person), 262170)
        self.assertEqual(travel_expenses({'travel': 10, 'expenses': 20, 'creditCard': 30}), 60)
        self.assertIsNone(travel_expenses({'travel': None, 'expenses': None}))
        self.assertEqual(travel_expenses({'expenses': 0}), 0)
        self.band['filings'][0]['people'] = [person]
        years = financial_years(self.band, self.capital)
        doc = html.fromstring(annual_page(self.band, '2023-2024', years['2023-2024'], years, slugify))
        cells = doc.xpath('//tbody/tr/td/text()')
        self.assertIn('$262,170', cells)
        self.assertEqual(cells.count('$262,170'), 1)
        self.assertEqual(cells[-1], '$0')

    def test_regeneration_preserves_lastmod_and_removes_only_owned_stale_page(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            initial, _ = publish(root, [self.band], self.capital, slugify)
            repeat, _ = publish(root, [self.band], self.capital, slugify)
            self.assertEqual(initial, repeat)
            unrelated = root/'first-nations/test-first-nation/map/index.html'
            unrelated.parent.mkdir(parents=True); unrelated.write_text('keep')
            self.band['filings'][0]['manual_review_required'] = True
            self.capital['bands']['1']['years']['2023-2024']['publishable'] = False
            current, _ = publish(root, [self.band], self.capital, slugify)
            self.assertNotIn('/first-nations/test-first-nation/financials/2023-2024/', current)
            self.assertFalse((root/'first-nations/test-first-nation/financials/2023-2024/index.html').exists())
            self.assertEqual(unrelated.read_text(), 'keep')

    def test_generated_pages_have_unique_canonicals_valid_schemas_and_links(self):
        manifest = json.loads((ROOT/'seo-page-manifest.json').read_text())
        canonicals, titles = set(), set()
        for path in manifest:
            with self.subTest(path=path):
                doc = html.parse(str(ROOT/path.strip('/')/'index.html'))
                canonical = doc.xpath('//link[@rel="canonical"]/@href')
                self.assertEqual(canonical, [ORIGIN+path])
                self.assertNotIn(canonical[0], canonicals); canonicals.add(canonical[0])
                title = doc.xpath('//title/text()')[0]
                self.assertNotIn(title, titles); titles.add(title)
                self.assertEqual(len(doc.xpath('//h1')), 1)
                for raw in doc.xpath('//script[@type="application/ld+json"]/text()'):
                    json.loads(raw)
                for href in doc.xpath('//a/@href'):
                    if href.startswith('/'):
                        target = ROOT/urlsplit(href).path.strip('/')/'index.html'
                        self.assertTrue(target.is_file(), href)
                if '/financials/' in path and path.startswith('/first-nations/'):
                    self.assertTrue(doc.xpath('//dl[@class="record-metrics"]|//tbody/tr'))
        sitemap = ET.parse(ROOT/'sitemap.xml')
        ns = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        locations = [node.text for node in sitemap.findall('s:url/s:loc', ns)]
        self.assertEqual(len(locations), len(set(locations)))
        self.assertTrue({ORIGIN+path for path in manifest}.issubset(locations))

    def test_schema_cannot_break_out_of_script(self):
        self.band['name'] = '</script><img src=x onerror=alert(1)>'
        years = financial_years(self.band, self.capital)
        page = annual_page(self.band, '2023-2024', years['2023-2024'], years, slugify)
        doc = html.fromstring(page)
        self.assertEqual(doc.xpath('//img'), [])
        json.loads(doc.xpath('//script[@type="application/ld+json"]/text()')[0])

if __name__ == '__main__':
    unittest.main()
