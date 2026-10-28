import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from tools.audit_community_updates import audit


class CommunityReadinessTests(unittest.TestCase):
    def make_root(self, root):
        datasets = {
            'data.json': {'bands': [{'id': 1, 'name': 'Example', 'province': 'SK'}, {'id': 2, 'name': 'Other', 'province': 'AB'}]},
            'news-data.json': {'articles': [{'id': 'news', 'bandId': 1, 'title': 'Community update', 'url': 'https://example.test/news', 'publishedAt': '2026-10-27'}]},
            'jobs-data.json': {'listings': [{'id': 'job', 'communityId': '2', 'firstNationIds': [], 'title': 'Housing Manager', 'employer': 'Other', 'sourceUrl': 'https://example.test/job', 'verifiedOfficialSource': True, 'status': 'Open', 'lastChecked': '2026-10-28', 'closingDate': '2026-11-01'}]},
            'events-data.json': {'events': []},
            'news-review-queue.json': {'items': [{'status': 'extracted', 'reason': 'Source extracted'}, {'status': 'manual_review', 'reason': 'Missing date'}]},
        }
        for name, payload in datasets.items():
            (root / name).write_text(json.dumps(payload))

    def test_counts_public_records_separately_from_review_history_without_writes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.make_root(root)
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            result = audit(root, date(2026, 10, 28))
            self.assertEqual(result['problems'], [])
            self.assertEqual(result['jobs']['verifiedActive'], 1)
            self.assertEqual(result['byProvince']['AB']['withPublicJobs'], 1)
            self.assertEqual(result['news']['reviewHistoryRecords'], 2)
            self.assertEqual(before, {p.name: p.read_bytes() for p in root.iterdir()})

    def test_unknown_ids_and_duplicate_identifiers_are_not_silently_accepted(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.make_root(root)
            news = json.loads((root / 'news-data.json').read_text())
            news['articles'].append({**news['articles'][0], 'bandId': 999})
            (root / 'news-data.json').write_text(json.dumps(news))
            result = audit(root, date(2026, 10, 28))
            self.assertEqual(len(result['problems']), 2)

    def test_stale_jobs_remain_pending_instead_of_being_counted_as_current(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.make_root(root)
            result = audit(root, date(2026, 12, 1))
            self.assertEqual(result['jobs']['public'], 0)


if __name__ == '__main__':
    unittest.main()
