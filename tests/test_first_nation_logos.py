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
        for band_id in ("397",):
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


class ManitobaLogoReviewTests(unittest.TestCase):
    def test_protected_logos_metadata_and_assets_are_unchanged(self):
        import hashlib
        from tools.manitoba_logos import digest
        baseline=json.loads((ROOT/'manual_overrides/manitoba-logo-baseline.json').read_text())
        data=json.loads((ROOT/'data.json').read_text())
        ids={str(b['id']) for b in data['bands'] if b.get('province')!='MB'}
        registry=json.loads((ROOT/'first-nation-logos.json').read_text())
        report=json.loads((ROOT/'first-nation-logo-report.json').read_text())
        self.assertEqual(baseline['registry'],digest([r for r in registry['logos'] if str(r['nation_id']) in ids]))
        self.assertEqual(baseline['report'],digest([r for r in report if str(r['nation_id']) in ids]))
        for url,sha in baseline['assets'].items():
            self.assertEqual(sha,hashlib.sha256((ROOT/url.lstrip('/')).read_bytes()).hexdigest())

    def test_every_verified_manitoba_asset_has_visual_and_hash_evidence(self):
        import hashlib
        from tools.manitoba_logos import digest
        reviews=json.loads((ROOT/'manual_overrides/manitoba-logo-reviews.json').read_text())
        approved={str(r['nation_id']):r for r in reviews['approvals']}
        data=json.loads((ROOT/'data.json').read_text())
        ids={str(b['id']) for b in data['bands'] if b.get('province')=='MB'}
        self.assertEqual(ids,{str(r['nation_id']) for r in reviews['nation_searches']})
        self.assertEqual(len(ids),63)
        registry=json.loads((ROOT/'first-nation-logos.json').read_text())
        for logo in registry['logos']:
            key=str(logo['nation_id'])
            if key not in ids or not logo['logo_verified']:continue
            review=approved[key]
            self.assertIs(review['visually_verified'],True)
            self.assertEqual(logo['visual_review']['review_sha256'],digest(review))
            self.assertEqual(logo['source_sha256'],review['source_sha256'])
            self.assertEqual(logo['sha256'],hashlib.sha256((ROOT/logo['logo_url'].lstrip('/')).read_bytes()).hexdigest())

    def test_review_rejects_automatic_or_changed_assets_and_wrong_nation(self):
        from tools.manitoba_logos import approved_review
        import hashlib
        review={'nation_id':295,'nation_name':'Dakota Tipi','visually_verified':True,
                'verification_note':'Visually inspected mark','identity_evidence':['Official Nation site'],
                'source_sha256':hashlib.sha256(b'original').hexdigest()}
        band={'id':295,'name':'Dakota Tipi','province':'MB'}
        self.assertTrue(approved_review(review,band,b'original'))
        for changed,b,payload in [(dict(review,visually_verified=False),band,b'original'),(review,band,b'changed'),(review,dict(band,id=296),b'original'),(review,dict(band,province='SK'),b'original')]:
            with self.assertRaises(ValueError):approved_review(changed,b,payload)


if __name__ == "__main__":
    unittest.main()
