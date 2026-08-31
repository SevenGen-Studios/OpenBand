import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class IntelligenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = (ROOT / "admin" / "intelligence" / "index.html").read_text(encoding="utf-8")
        cls.client = (ROOT / "assets" / "intelligence-admin.js").read_text(encoding="utf-8")
        cls.worker = (ROOT / "analytics-worker" / "src" / "index.ts").read_text(encoding="utf-8")
        cls.engine = (ROOT / "analytics-worker" / "src" / "intelligence.ts").read_text(encoding="utf-8")

    def test_admin_page_is_not_indexable_and_requires_authentication(self):
        self.assertIn('content="noindex,nofollow,noarchive"', self.page)
        self.assertIn("Administrator authentication is required", self.page)
        self.assertIn("Manual verification required", self.page)
        self.assertNotIn("ANALYTICS_ADMIN_TOKEN", self.page)
        self.assertNotIn("Bearer ", self.page)

    def test_token_stays_in_memory_and_api_is_server_protected(self):
        self.assertIn('let adminToken=""', self.client)
        self.assertNotIn("localStorage", self.client)
        self.assertNotIn("sessionStorage", self.client)
        self.assertIn("Authorization:`Bearer ${adminToken}`", self.client)
        self.assertIn('url.pathname === "/v1/intelligence"', self.worker)
        self.assertIn("if (!authorize(request, env))", self.worker)

    def test_engine_preserves_categories_missingness_and_provenance(self):
        self.assertIn("otherPayments: amount(person.otherPayments)", self.engine)
        self.assertIn("travel: amount(person.travel)", self.engine)
        self.assertIn("completeSum", self.engine)
        self.assertIn("sourceRecordIndex", self.engine)
        self.assertIn("sourceUrl", self.engine)
        self.assertIn("requiresManualVerification: true", self.engine)

    def test_expected_metrics_signals_and_filters_are_present(self):
        for value in [
            "nonRemunerationAmount", "expensesPercentage", "remunerationPercentage",
            "otherPaymentsPercentage", "nonRemunerationPercentage", "yoy", "threeYearChange", "trends",
            "expense_heavy", "other_payment_heavy", "large_yoy_change", "high_total",
            "extreme_one_year_value", "multi_year_trend", "data_anomaly",
        ]:
            with self.subTest(value=value):
                self.assertIn(value, self.engine)
        for section in ["overview", "leads", "officials", "nations", "quality"]:
            with self.subTest(section=section):
                self.assertIn(f'section === "{section}"', self.worker)


if __name__ == "__main__":
    unittest.main()
