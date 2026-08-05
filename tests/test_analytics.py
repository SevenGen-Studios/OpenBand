import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AnalyticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = (ROOT / "assets" / "analytics.js").read_text(encoding="utf-8")
        cls.app = (ROOT / "assets" / "openband.js").read_text(encoding="utf-8")
        cls.worker = (ROOT / "analytics-worker" / "src" / "index.ts").read_text(encoding="utf-8")
        cls.schema = (ROOT / "analytics-worker" / "schema.sql").read_text(encoding="utf-8")

    def test_client_is_production_only_and_respects_do_not_track(self):
        self.assertIn("productionHosts.includes(location.hostname)", self.client)
        self.assertIn('navigator.doNotTrack!=="1"', self.client)
        self.assertIn("config.enabled&&production", self.client)
        self.assertIn("sessionId=permitted?", self.client)
        self.assertIn("visitorId=permitted?", self.client)

    def test_client_batches_retries_and_lazy_loads_ga(self):
        self.assertIn("queue.length>=10", self.client)
        self.assertIn("retryDelay=Math.min", self.client)
        self.assertIn("requestIdleCallback", self.client)
        self.assertIn("navigator.sendBeacon", self.client)
        self.assertIn("send_page_view:false", self.client)

    def test_required_events_are_centralized(self):
        for event in [
            "search_performed", "community_view", "statement_opened",
            "statement_downloaded", "community_capital_view",
            "revenue_chart_viewed", "expense_chart_viewed",
            "comparison_completed", "news_article_opened",
            "outbound_link_clicked", "pdf_failed_to_load", "parser_error",
        ]:
            with self.subTest(event=event):
                self.assertIn(event, self.worker)
        self.assertIn("window.OpenBandAnalytics=service", self.client)
        self.assertIn("window.OpenBandAnalytics?.trackSearch", self.app)
        self.assertIn("window.OpenBandAnalytics?.trackCommunityView", self.app)

    def test_internal_schema_has_no_ip_or_personal_fields(self):
        lowered = self.schema.lower()
        self.assertNotIn("ip_address", lowered)
        self.assertNotIn("email", lowered)
        self.assertNotIn("user_name", lowered)
        self.assertIn("visitor_id", lowered)
        self.assertIn("session_id", lowered)
        self.assertIn("country", lowered)
        self.assertIn("province", lowered)
        self.assertNotIn("cf-connecting-ip", self.worker.lower())

    def test_worker_hashes_visitors_and_secures_reporting(self):
        self.assertIn('crypto.subtle.digest("SHA-256"', self.worker)
        self.assertIn("ANALYTICS_ADMIN_TOKEN", self.worker)
        self.assertIn('url.pathname === "/v1/dashboard"', self.worker)
        self.assertIn("containsPersonalData", self.worker)

    def test_admin_route_is_not_indexable(self):
        markup = (ROOT / "admin" / "analytics" / "index.html").read_text(encoding="utf-8")
        self.assertIn('content="noindex,nofollow,noarchive"', markup)
        self.assertIn("Administrator authentication is required", markup)


if __name__ == "__main__":
    unittest.main()
