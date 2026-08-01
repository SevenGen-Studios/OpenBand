import json
import html
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.build_site import ORIGIN, build, slugify  # noqa: E402


class SiteRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        build()
        cls.data = json.loads((ROOT / "data.json").read_text(encoding="utf-8"))

    def test_slug_generation_is_stable(self):
        cases = {
            "Keeseekoose First Nation": "keeseekoose-first-nation",
            "Beardy's & Okemasis Cree Nation": "beardys-and-okemasis-cree-nation",
            "Mistawasis Nêhiyawak": "mistawasis-nehiyawak",
            "Mosquito, Grizzly Bear's Head, Lean Man First Nation": "mosquito-grizzly-bears-head-lean-man-first-nation",
        }
        for name, expected in cases.items():
            with self.subTest(name=name):
                self.assertEqual(slugify(name), expected)

    def test_every_band_has_a_static_profile(self):
        for band in self.data["bands"]:
            page = ROOT / "first-nations" / slugify(band["name"]) / "index.html"
            self.assertTrue(page.is_file(), band["name"])
            markup = page.read_text(encoding="utf-8")
            expected_title = html.escape(f"{band['name']} Financial Records | OpenBand")
            self.assertIn(f"<title>{expected_title}</title>", markup)
            self.assertIn(f'{ORIGIN}/first-nations/{slugify(band["name"])}/', markup)
            self.assertIn(f'data-band-id="{band["id"]}"', markup)
            expected_heading = html.escape(f"{band['name']} Financial Records")
            self.assertIn(f"<h1>{expected_heading}</h1>", markup)

    def test_indexable_routes_and_seo_files_exist(self):
        for relative in ["browse/index.html", "news/index.html", "robots.txt", "sitemap.xml", "assets/favicon.svg", "assets/openband-social.png"]:
            self.assertTrue((ROOT / relative).is_file(), relative)
        sitemap = (ROOT / "sitemap.xml").read_text(encoding="utf-8")
        self.assertEqual(sitemap.count("<url>"), len(self.data["bands"]) + 3)
        self.assertIn(f"{ORIGIN}/browse/", sitemap)
        self.assertIn(f"{ORIGIN}/news/", sitemap)

    def test_public_pages_share_dynamic_copyright_footer(self):
        pages = [ROOT / "index.html", ROOT / "browse" / "index.html", ROOT / "news" / "index.html"]
        pages.extend((ROOT / "first-nations").glob("*/index.html"))
        self.assertGreater(len(pages), 3)
        for page in pages:
            with self.subTest(page=page):
                markup = page.read_text(encoding="utf-8")
                self.assertIn("<footer>", markup)
                self.assertIn("&copy; <span data-current-year>2026</span> OpenBand. All rights reserved.", markup)
        javascript = (ROOT / "assets" / "openband.js").read_text(encoding="utf-8")
        self.assertIn("document.querySelectorAll('[data-current-year]')", javascript)

    def test_shared_assets_and_route_restoration_hooks(self):
        profile = (ROOT / "first-nations" / "keeseekoose-first-nation" / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="/assets/openband.css?v=20260801c"', profile)
        self.assertIn('src="/assets/openband.js?v=20260801c"', profile)
        javascript = (ROOT / "assets" / "openband.js").read_text(encoding="utf-8")
        self.assertIn("function profilePath", javascript)
        self.assertIn("function restoreRoute", javascript)
        self.assertIn("window.addEventListener('popstate'", javascript)
        self.assertIn("activeProfileTab='overview'", javascript)
        self.assertIn("function getRevenueHistory", javascript)
        self.assertIn("Where the Revenue Came From", javascript)
        self.assertIn("revenue-segment", javascript)
        self.assertIn("setRevenueMode", javascript)
        self.assertIn("setRevenueFocus", javascript)
        self.assertIn("Revenue sources reconcile", javascript)
        self.assertIn("revenue-source-browser", javascript)
        self.assertIn("revenue-year-body", javascript)
        self.assertIn("breakdowns.after(section)", javascript)


if __name__ == "__main__":
    unittest.main()
