import unittest

from tools.build_audit_partnerships import build_partnerships


class AuditPartnershipTests(unittest.TestCase):
    def setUp(self):
        self.enterprise = {
            "organizations": [{
                "id": "org-kitsaki", "name": "Kitsaki Management Limited Partnership",
                "organizationType": "Economic development organization",
                "description": "A reviewed organization.", "sourceIds": ["source-kitsaki"],
            }],
            "businesses": [],
            "organizationRelationships": [{
                "parentType": "firstNation", "parentId": "band-353",
                "childId": "org-kitsaki", "relationshipType": "economic development arm",
                "verificationStatus": "Verified", "sourceIds": ["source-kitsaki"],
            }],
            "tribalCouncilOrganizations": [],
            "sources": [{
                "id": "source-kitsaki", "title": "About", "publisher": "Kitsaki",
                "url": "https://example.test/kitsaki", "lastVerified": "2026-08-14",
            }],
        }
        self.lead = {
            "firstNationIds": ["353"], "fiscalYear": "2024-2025",
            "originalLabel": "Kitsaki Management Limited Partnership - 99.9%",
            "currentYearAmount": 51_772_359,
            "sourceDocument": {"url": "https://example.test/audit.pdf"},
            "sourceReferences": [{"pdfPage": 18, "table": "Investments"}],
        }

    def test_corroborated_audit_entity_is_publishable(self):
        rows = build_partnerships([self.lead], self.enterprise, {"communities": []})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "Kitsaki Management Limited Partnership")
        self.assertEqual(rows[0]["latestAuditDisclosure"]["reportedAmount"], 51_772_359)
        self.assertEqual(len(rows[0]["sources"]), 1)

    def test_same_entity_text_is_not_assigned_to_another_nation(self):
        lead = {**self.lead, "firstNationIds": ["400"]}
        self.assertEqual(build_partnerships([lead], self.enterprise, {"communities": []}), [])


if __name__ == "__main__":
    unittest.main()
