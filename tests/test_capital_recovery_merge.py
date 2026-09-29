import unittest
from tools.merge_capital_recovery import merge_recovery


class RecoveryMergeTests(unittest.TestCase):
    def candidate(self):
        return {"parseStatus": "parsed", "publishable": True, "sourceUrl": "https://example.test/source.pdf",
                "fiscalYear": "2024-2025", "totalRevenue": 100, "totalExpenses": 80,
                "annualSurplusDeficit": 20,
                "revenueBreakdown": [{"amount": 60}, {"amount": 40}],
                "expenseBreakdown": [{"amount": 50}, {"amount": 30}]}

    def dataset(self, summary):
        return {"bands": {"464": {"name": "Cold Lake", "years": {"2024-2025": summary}}}}

    def test_valid_candidate_replaces_pending_without_mutation(self):
        current = self.dataset({"publishable": False})
        merged, accepted = merge_recovery(current, self.dataset(self.candidate()))
        self.assertEqual(len(accepted), 1)
        self.assertTrue(merged["bands"]["464"]["years"]["2024-2025"]["publishable"])
        self.assertFalse(current["bands"]["464"]["years"]["2024-2025"]["publishable"])

    def test_existing_usable_data_is_preserved(self):
        current = self.dataset(self.candidate())
        self.assertEqual(merge_recovery(current, current)[1], [])

    def test_claimed_publishable_but_invalid_is_rejected(self):
        candidate = self.candidate()
        candidate["totalExpenses"] = 50
        self.assertEqual(merge_recovery(self.dataset({}), self.dataset(candidate))[1], [])

    def test_wrong_year_is_rejected(self):
        candidate = self.candidate()
        candidate["fiscalYear"] = "2023-2024"
        self.assertEqual(merge_recovery(self.dataset({}), self.dataset(candidate))[1], [])
