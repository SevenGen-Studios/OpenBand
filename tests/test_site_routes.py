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
        for relative in ["browse/index.html", "news/index.html", "admin/index.html", "admin/analytics/index.html", "robots.txt", "sitemap.xml", "map-data.json", "assets/favicon.svg", "assets/openband-social.png", "assets/analytics.js", "assets/analytics-config.js"]:
            self.assertTrue((ROOT / relative).is_file(), relative)
        sitemap = (ROOT / "sitemap.xml").read_text(encoding="utf-8")
        self.assertEqual(sitemap.count("<url>"), len(self.data["bands"]) + 3)
        self.assertIn(f"{ORIGIN}/browse/", sitemap)
        self.assertIn(f"{ORIGIN}/news/", sitemap)
        self.assertNotIn("/admin/", sitemap)
        self.assertIn("Disallow: /admin/", (ROOT / "robots.txt").read_text(encoding="utf-8"))

    def test_admin_portal_links_operational_services_without_credentials(self):
        portal = (ROOT / "admin" / "index.html").read_text(encoding="utf-8")
        self.assertIn('content="noindex,nofollow,noarchive"', portal)
        self.assertIn('href="/admin/analytics/"', portal)
        self.assertIn("analytics.google.com", portal)
        self.assertIn("openband-analytics", portal)
        self.assertIn("workers/d1/databases", portal)
        self.assertIn("github.com/Sheekee011/openband-v2/actions", portal)
        self.assertNotIn("ANALYTICS_ADMIN_TOKEN", portal)
        self.assertNotIn("Bearer ", portal)

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
        self.assertIn('href="/assets/openband.css?v=20260810g"', profile)
        self.assertIn('src="/assets/openband.js?v=20260810g"', profile)
        self.assertIn('src="/assets/analytics.js?v=20260805b"', profile)
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
        self.assertIn("function renderUnverifiedProjectsSection", javascript)
        self.assertIn("function toggleUnverifiedProjects", javascript)
        self.assertIn("Unverified Projects &amp; Community Discussion", javascript)
        self.assertIn("Revenue sources reconcile", javascript)
        self.assertIn("revenue-source-browser", javascript)
        self.assertIn("revenue-year-body", javascript)
        self.assertIn("breakdowns.after(section)", javascript)
        self.assertIn("function renderHousingProjectsSection", javascript)
        self.assertIn("function toggleProjects", javascript)
        self.assertIn("['capital','Community Capital'],['projects','Housing & Infrastructure'],['sources','Source Documents']", javascript)
        self.assertIn("else if(activeProfileTab==='projects')", javascript)

    def test_every_profile_has_projects_section(self):
        for band in self.data["bands"]:
            page = ROOT / "first-nations" / slugify(band["name"]) / "index.html"
            with self.subTest(band=band["name"]):
                markup = page.read_text(encoding="utf-8")
                self.assertEqual(markup.count("Housing &amp; Infrastructure Projects"), 1)

    def test_browse_page_uses_official_interactive_map_data(self):
        markup = (ROOT / "browse" / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="directoryMap"', markup)
        self.assertIn('id="tribalCouncilFilter"', markup)
        self.assertIn('data-map-mode="treaty"', markup)
        self.assertIn('data-map-mode="tribalCouncil"', markup)
        self.assertNotIn('id="azLinks"', markup)
        self.assertIn('class="map-list-fallback"', markup)
        map_data = json.loads((ROOT / "map-data.json").read_text(encoding="utf-8"))
        self.assertEqual(map_data["communityCount"], len(self.data["bands"]))
        self.assertFalse(map_data["missingLocations"])
        mapped_ids = {str(row["id"]) for row in map_data["communities"]}
        self.assertEqual(mapped_ids, {str(row["id"]) for row in self.data["bands"]})
        for row in map_data["communities"]:
            self.assertGreaterEqual(row["latitude"], 48.5)
            self.assertLessEqual(row["latitude"], 60.5)
            self.assertGreaterEqual(row["longitude"], -111.5)
            self.assertLessEqual(row["longitude"], -100.5)
        javascript = (ROOT / "assets" / "openband.js").read_text(encoding="utf-8")
        self.assertIn("function renderDirectoryMap", javascript)
        self.assertIn("function loadMapData", javascript)
        self.assertIn("location.assign(profilePath(band.name))", javascript)
        self.assertIn("maxBounds:PRAIRIE_MAP_BOUNDS", javascript)
        self.assertIn("scrollWheelZoom:true", javascript)
        self.assertIn("wheelPxPerZoomLevel:140", javascript)
        self.assertIn("radius:9", javascript)
        self.assertIn("maxZoom:8", javascript)
        councils = {row["tribalCouncil"] for row in map_data["communities"]}
        self.assertIn("South East Treaty 4 Tribal Council", councils)
        self.assertIn("Battlefords Agency Tribal Chiefs (BATC)", councils)
        self.assertNotIn("Battlefords Tribal Council (BTC)", councils)

    def test_election_prerender_is_available_for_every_nation(self):
        seeded = (ROOT / "first-nations" / "beardys-and-okemasis-cree-nation" / "index.html").read_text(encoding="utf-8")
        self.assertIn("Elections &amp; Leadership", seeded)
        self.assertIn("Edwin Ananas", seeded)
        for band in self.data["bands"]:
            page = ROOT / "first-nations" / slugify(band["name"]) / "index.html"
            with self.subTest(band=band["name"]):
                self.assertEqual(page.read_text(encoding="utf-8").count("Elections &amp; Leadership"), 1)
        self.assertIn("if(el('profilePrerender'))el('profilePrerender').hidden=true", (ROOT / "assets" / "openband.js").read_text(encoding="utf-8"))

    def test_election_records_are_complete_and_source_linked(self):
        elections = json.loads((ROOT / "elections-data.json").read_text(encoding="utf-8"))
        band_ids = {band["id"] for band in self.data["bands"]}
        required = {"firstNationId", "firstNation", "electionDate", "candidateName", "position", "votesReceived", "elected", "sourceUrl"}
        self.assertEqual({record["firstNationId"] for record in elections["records"]}, band_ids)
        record_keys = {
            (record["firstNationId"], record["electionDate"], record["candidateName"], record["position"])
            for record in elections["records"]
        }
        self.assertEqual(len(record_keys), len(elections["records"]))
        for record in elections["records"]:
            with self.subTest(record=record):
                self.assertTrue(required.issubset(record))
                self.assertIn(record["firstNationId"], band_ids)
                self.assertIn(record["position"], {"Chief", "Councillor"})
                self.assertIs(record["elected"], True)
                self.assertRegex(record["electionDate"], r"^\d{4}-\d{2}-\d{2}$")
                self.assertGreaterEqual(record["electionDate"], "2021-08-10")
                self.assertTrue(record["candidateName"].strip())
                self.assertTrue(record["sourceUrl"].startswith("https://"))
                if record["votesReceived"] is not None:
                    self.assertIsInstance(record["votesReceived"], int)
                    self.assertGreater(record["votesReceived"], 0)

        for band_id in band_ids:
            latest_date = max(
                record["electionDate"]
                for record in elections["records"]
                if record["firstNationId"] == band_id
            )
            latest = [
                record
                for record in elections["records"]
                if record["firstNationId"] == band_id and record["electionDate"] == latest_date
            ]
            with self.subTest(band_id=band_id, election_date=latest_date):
                self.assertIn("Chief", {record["position"] for record in latest})
                self.assertIn("Councillor", {record["position"] for record in latest})

    def test_missing_vote_totals_are_not_rendered_as_zero(self):
        markup = (ROOT / "first-nations" / "muskoday-first-nation" / "index.html").read_text(encoding="utf-8")
        self.assertIn("Ronald Bear", markup)
        self.assertIn("167 votes", markup)
        self.assertIn("Elwin Bear", markup)
        self.assertNotIn("0 votes", markup)
        javascript = (ROOT / "assets" / "openband.js").read_text(encoding="utf-8")
        self.assertIn("record.votesReceived!==null", javascript)

    def test_ga4_tag_is_present_on_every_public_page(self):
        pages = [ROOT / "index.html", ROOT / "browse" / "index.html", ROOT / "news" / "index.html"]
        pages.extend((ROOT / "first-nations").glob("*/index.html"))
        for page in pages:
            with self.subTest(page=page):
                markup = page.read_text(encoding="utf-8")
                self.assertEqual(markup.count("googletagmanager.com/gtag/js?id=G-JYWTEVQ5JG"), 1)
                self.assertIn("send_page_view:false", markup)


if __name__ == "__main__":
    unittest.main()
