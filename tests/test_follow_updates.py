import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from tools.build_follow_updates import build


class FollowUpdatesTests(unittest.TestCase):
    def test_build_keeps_real_changes_and_ignores_refreshes_and_expired_jobs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data.json").write_text(json.dumps({"bands": [
                {"id": 261, "name": "Brokenhead Ojibway Nation", "province": "MB"},
                {"id": 362, "name": "Kahkewistahaw First Nation", "province": "SK"},
                {"id": 430, "name": "Siksika Nation", "province": "AB"},
                {"id": 500, "name": "Quiet community", "province": "MB"},
            ]}))
            def put(name, key, rows):
                (root / f"{name}-data.json").write_text(json.dumps({key: rows}))

            first = datetime(2026, 11, 7, tzinfo=timezone.utc)
            later = datetime(2026, 11, 8, tzinfo=timezone.utc)
            event = {"id": "event-1", "bandId": 362, "title": "Community workshop",
                     "startDate": "2026-11-12", "description": "Date: 2026-11-12.",
                     "sourceUrl": "https://example.org/events/workshop"}
            job = {"id": "job-1", "communityId": "261", "title": "Teacher", "employer": "School",
                   "lastChecked": "2026-11-07", "closingDate": "2026-11-12",
                   "verifiedOfficialSource": True, "status": "Open", "sourceUrl": "https://example.org/jobs/teacher"}
            news = {"id": "article-1", "bandId": 430, "title": "Community announcement",
                    "url": "https://example.org/news/announcement", "publishedAt": "2026-11-07"}
            project = {"id": "project-1", "firstNationIds": ["362"], "name": "Community centre",
                       "status": "Completed", "statusAsOf": "2026-11-07",
                       "sources": [{"url": "https://example.org/projects/centre"}]}
            put("events", "events", [event])
            put("news", "articles", [news, {**news, "id": "duplicate", "url": news["url"] + "/"},
                                     {**news, "id": "other", "bandId": 99}])
            put("jobs", "listings", [job, {**job, "id": "expired", "closingDate": "2026-11-06",
                                          "sourceUrl": "https://example.org/jobs/expired"}])
            put("projects", "projects", [project, {**project, "id": "undated", "statusAsOf": None}])
            initial = build(root, first)
            self.assertCountEqual([row["kind"] for row in initial["updates"]], ["events", "jobs", "news", "projects"])
            self.assertEqual(len(initial["communities"]), 4)
            self.assertEqual(json.loads((root / "follow-data/500.json").read_text())["updates"], [])
            self.assertEqual(len(json.loads((root / "follow-data/362.json").read_text())["updates"]), 2)
            put("jobs", "listings", [{**job, "lastChecked": "2026-11-08"}])
            self.assertEqual(build(root, later), initial)

            put("jobs", "listings", [])
            self.assertEqual(len(build(root, later)["updates"]), 3)
            put("jobs", "listings", [job])
            self.assertEqual(build(root, later), initial)

            put("events", "events", [{**event, "location": "Community hall"}])
            updated = build(root, later)
            original = next(row for row in initial["updates"] if row["kind"] == "events")
            moved = next(row for row in updated["updates"] if row["kind"] == "events")
            self.assertEqual(moved["id"], original["id"])
            self.assertNotEqual(moved["revision"], original["revision"])
            self.assertEqual(moved["updatedAt"], later.isoformat())
            self.assertEqual(moved["firstSeenAt"], first.isoformat())
            self.assertEqual(build(root, later), updated)

            put("projects", "projects", [{**project, "statusAsOf": "2026-11-08"}])
            rechecked = next(row for row in build(root, later)["updates"] if row["kind"] == "projects")
            self.assertEqual(rechecked["updatedAt"], first.isoformat())

            put("jobs", "listings", [
                {**job, "sourceUrl": "https://example.org/careers/#job-1"},
                {**job, "id": "job-2", "sourceUrl": "https://example.org/careers/#job-2"},
            ])
            self.assertEqual(sum(row["kind"] == "jobs" for row in build(root, later)["updates"]), 2)
