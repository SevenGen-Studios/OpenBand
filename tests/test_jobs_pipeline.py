import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from tools.jobs_collector import collect, effective_status, expand_verified_batches, listing_key, normalize_listing


ROOT = Path(__file__).resolve().parents[1]


class JobsPipelineTests(unittest.TestCase):
    def test_closing_dates_control_public_status(self):
        today = date(2026, 8, 11)
        base = {"status": "Open", "lastChecked": "2026-08-11"}
        self.assertEqual(effective_status({**base, "closingDate": "2026-08-10"}, today), "Closed")
        self.assertEqual(effective_status({**base, "closingDate": "2026-08-12"}, today), "Closing soon")
        self.assertEqual(effective_status({**base, "closingDate": "2026-09-01"}, today), "Open")

    def test_stale_undated_opening_requires_verification(self):
        status = effective_status(
            {"status": "Open", "closingDate": None, "lastChecked": "2026-07-01"},
            date(2026, 8, 11),
        )
        self.assertEqual(status, "Pending verification")

    def test_missing_money_is_not_converted_to_zero(self):
        record = normalize_listing(
            {
                "title": "Program Worker",
                "employer": "Example First Nation",
                "sourceUrl": "https://example.test/jobs",
                "status": "Open",
                "lastChecked": "2026-08-11",
                "verifiedOfficialSource": True,
            },
            date(2026, 8, 11),
        )
        self.assertIsNone(record["salary"])
        self.assertIsNone(record["closingDate"])

    def test_manual_override_wins_and_duplicates_are_suppressed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_record = {
                "id": "generated-worker",
                "title": "Program Worker",
                "employer": "Example First Nation",
                "communityId": "1",
                "location": "Example, Saskatchewan",
                "sourceUrl": "https://example.test/jobs/generated",
                "status": "Pending verification",
                "lastChecked": "2026-08-11",
            }
            manual_record = {
                **source_record,
                "id": "manual-worker",
                "sourceUrl": "https://example.test/jobs/verified",
                "status": "Open",
                "verifiedOfficialSource": True,
                "extractionConfidence": "high",
                "manualOverride": True,
            }
            (root / "jobs-sources.json").write_text('{"sources": []}', encoding="utf-8")
            (root / "jobs-data.json").write_text(json.dumps({"listings": [source_record]}), encoding="utf-8")
            (root / "jobs-overrides.json").write_text(json.dumps({"manualListings": [manual_record]}), encoding="utf-8")
            data, report = collect(root, date(2026, 8, 11), offline=True)
            self.assertEqual(len(data["listings"]), 1)
            self.assertTrue(data["listings"][0]["manualOverride"])
            self.assertEqual(data["listings"][0]["status"], "Open")
            self.assertEqual(report["duplicatesSuppressed"], 1)

    def test_verified_batches_expand_without_losing_regional_scope(self):
        rows = expand_verified_batches({
            "verifiedBatches": [{
                "sourceId": "regional-board",
                "employer": "Regional Council",
                "firstNationIds": ["1", "2"],
                "jobs": [{"id": "regional-worker", "title": "Program Worker"}],
            }]
        })
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["firstNationIds"], ["1", "2"])
        self.assertTrue(rows[0]["manualOverride"])

    def test_every_tracked_community_has_source_coverage(self):
        data, report = collect(ROOT, date(2026, 8, 11), offline=True)
        self.assertEqual(len(data["communityCoverage"]), 69)
        self.assertEqual(report["trackedCommunities"], 69)
        self.assertEqual(report["communitiesWithSourceCoverage"], 69)
        self.assertTrue(all(row["sources"] for row in data["communityCoverage"]))

    def test_regional_listing_is_counted_for_each_member_community(self):
        data, _ = collect(ROOT, date(2026, 8, 11), offline=True)
        by_id = {row["communityId"]: row for row in data["communityCoverage"]}
        self.assertGreater(by_id["377"]["activeListings"], 0)
        self.assertGreater(by_id["374"]["activeListings"], 0)

    def test_seed_data_is_source_linked_and_unique(self):
        payload = json.loads((ROOT / "jobs-data.json").read_text(encoding="utf-8"))
        keys = [listing_key(row) for row in payload["listings"]]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertTrue(payload["listings"])
        for row in payload["listings"]:
            self.assertTrue(row["sourceUrl"].startswith("https://"))
            self.assertTrue(row["verifiedOfficialSource"])
            self.assertNotEqual(row.get("salary"), 0)


if __name__ == "__main__":
    unittest.main()
