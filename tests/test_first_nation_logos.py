import html
import json
import unittest
from pathlib import Path

from tools.merge_previous_data import merge_band


ROOT = Path(__file__).resolve().parents[1]


class FirstNationLogoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((ROOT / "data.json").read_text(encoding="utf-8"))
        cls.registry = json.loads((ROOT / "first-nation-logos.json").read_text(encoding="utf-8"))
        cls.report = json.loads((ROOT / "first-nation-logo-report.json").read_text(encoding="utf-8"))
        cls.logos = {str(row["nation_id"]): row for row in cls.registry["logos"]}

    def test_every_database_nation_has_a_logo_record(self):
        band_ids = {str(band["id"]) for band in self.data["bands"]}
        self.assertEqual(band_ids, set(self.logos))
        self.assertEqual(len(band_ids), self.registry["recordCount"])
        self.assertEqual(
            self.registry["recordCount"],
            self.registry["verifiedCount"] + self.registry["unverifiedCount"],
        )
        self.assertEqual(self.registry["recordCount"], len(self.report))

    def test_logo_metadata_is_synced_to_main_data(self):
        for band in self.data["bands"]:
            logo = self.logos[str(band["id"])]
            for key in ("logo_url", "logo_source", "logo_asset_source", "logo_verified", "logo_status"):
                self.assertIn(key, band, f"{band['name']} is missing {key}")
                self.assertEqual(band[key], logo[key])

    def test_verified_assets_are_local_optimized_and_sourced(self):
        for logo in self.logos.values():
            if not logo["logo_verified"]:
                self.assertIsNone(logo["logo_url"])
                self.assertEqual("logo_unverified", logo["logo_status"])
                continue
            self.assertEqual("verified", logo["logo_status"])
            self.assertTrue(logo["logo_source"].startswith(("http://", "https://")))
            self.assertTrue(logo["logo_asset_source"].startswith(("http://", "https://")))
            self.assertTrue(logo["logo_url"].startswith("/public/first-nation-logos/"))
            asset = ROOT / logo["logo_url"].lstrip("/")
            self.assertTrue(asset.is_file(), f"Missing {asset}")
            self.assertIn(asset.suffix.lower(), {".webp", ".svg"})
            self.assertLess(asset.stat().st_size, 512_000, f"Logo is not web-sized: {asset}")

    def test_visually_rejected_false_positives_stay_unverified(self):
        for band_id in ("397", "385", "345"):
            self.assertFalse(self.logos[band_id]["logo_verified"])

    def test_generated_profiles_render_logo_or_placeholder(self):
        for band in self.data["bands"]:
            logo = self.logos[str(band["id"])]
            slug = logo["slug"]
            page = (ROOT / "first-nations" / slug / "index.html").read_text(encoding="utf-8")
            self.assertIn("profile-prerender-title", page)
            if logo["logo_verified"]:
                self.assertIn(logo["logo_url"], page)
                self.assertIn(html.escape(f"{band['name']} official logo", quote=True), page)
                title_markup = page.split("profile-prerender-title", 1)[1].split("</div>", 1)[0]
                self.assertNotIn("fn-logo-initials", title_markup)
            else:
                self.assertIn("fn-logo-unverified", page)
                self.assertIn("logo unverified; OpenBand placeholder", page)

    def test_logo_surfaces_and_containment_styles_are_present(self):
        script = (ROOT / "assets" / "openband.js").read_text(encoding="utf-8")
        styles = (ROOT / "assets" / "openband.css").read_text(encoding="utf-8")
        for marker in ("nationLogoMarkup", "recent-main", "directory-community-main", "aci-copy"):
            self.assertIn(marker, script)
        self.assertIn("border-radius:50%", styles)
        self.assertIn("object-fit:contain", styles)

    def test_incremental_scraper_merge_preserves_logo_metadata(self):
        previous = {
            "logo_url": "/public/first-nation-logos/example.webp",
            "logo_source": "https://example.test/",
            "logo_asset_source": "https://example.test/logo.png",
            "logo_verified": True,
            "logo_status": "verified",
            "filings": [],
        }
        current = {"filings": []}
        merge_band(previous, current)
        for key in (
            "logo_url",
            "logo_source",
            "logo_asset_source",
            "logo_verified",
            "logo_status",
        ):
            self.assertEqual(previous[key], current[key])


if __name__ == "__main__":
    unittest.main()
