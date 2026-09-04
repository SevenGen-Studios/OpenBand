import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ProjectsIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bands = json.loads((ROOT / "data.json").read_text(encoding="utf-8"))["bands"]
        cls.payload = json.loads((ROOT / "projects-data.json").read_text(encoding="utf-8"))
        cls.projects = cls.payload["projects"]
        cls.disclosures = cls.payload.get("financialDisclosures", [])
        cls.unverified = cls.payload["unverifiedProjects"]

    def test_schema_and_project_ids(self):
        self.assertEqual(self.payload["schemaVersion"], 1)
        self.assertRegex(self.payload["generatedAt"], r"^\d{4}-\d{2}-\d{2}$")
        ids = [project["id"] for project in self.projects]
        self.assertEqual(len(ids), len(set(ids)))

    def test_all_communities_are_in_the_public_source_audit(self):
        audit = self.payload["sourceAudit"]
        registry = json.loads((ROOT / audit["registry"]).read_text(encoding="utf-8"))
        self.assertEqual(audit["communityCount"], len(self.bands))
        self.assertEqual(len(registry["communities"]), len(self.bands))
        self.assertEqual(
            {str(row["bandId"]) for row in registry["communities"]},
            {str(band["id"]) for band in self.bands},
        )
        for row in registry["communities"]:
            self.assertTrue(row.get("discoveryQueries"))
            self.assertTrue(any("facebook.com" in query for query in row["discoveryQueries"]))
            self.assertTrue(any("housing OR infrastructure" in query for query in row["discoveryQueries"]))

    def test_projects_are_source_linked_to_known_nations(self):
        band_ids = {str(band["id"]) for band in self.bands}
        allowed_statuses = {"Planned", "Under Construction", "Completed"}
        date_pattern = re.compile(r"^\d{4}(?:-\d{2})?(?:-\d{2})?$")
        for project in self.projects:
            with self.subTest(project=project["id"]):
                self.assertTrue(project["name"].strip())
                self.assertTrue(project["description"].strip())
                self.assertTrue(project["firstNationIds"])
                self.assertTrue({str(value) for value in project["firstNationIds"]}.issubset(band_ids))
                if project.get("status"):
                    self.assertIn(project["status"], allowed_statuses)
                    self.assertRegex(project["statusAsOf"], date_pattern)
                self.assertRegex(project["lastVerifiedAt"], r"^\d{4}-\d{2}-\d{2}$")
                self.assertTrue(project["sources"])
                for source in project["sources"]:
                    self.assertTrue(source["name"].strip())
                    self.assertTrue(source["url"].startswith("https://"))
                    self.assertTrue(source.get("publishedAt") or source.get("checkedAt"))
                    if source.get("publishedAt"):
                        self.assertRegex(source["publishedAt"], date_pattern)
                    if source.get("checkedAt"):
                        self.assertRegex(source["checkedAt"], r"^\d{4}-\d{2}-\d{2}$")

    def test_optional_fields_are_omitted_instead_of_placeholder_values(self):
        forbidden = {"unknown", "n/a", "not available", "tbd", "to be determined"}
        for project in self.projects:
            with self.subTest(project=project["id"]):
                for key in ("estimatedCost", "startDate", "completionDate", "unitsCapacity"):
                    if key in project:
                        self.assertNotIn(str(project[key]).strip().lower(), forbidden)

    def test_project_coverage_expanded_after_all_community_audit(self):
        covered = {str(band_id) for project in self.projects for band_id in project["firstNationIds"]}
        self.assertGreaterEqual(len(covered), 35)

    def test_audited_project_disclosures_are_source_linked_and_do_not_infer_status(self):
        band_ids = {str(band["id"]) for band in self.bands}
        ids = [row["id"] for row in self.disclosures]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertGreaterEqual(len(self.disclosures), 13)
        allowed_amounts = {
            "fundingReceived", "revenueRecognized", "deferredRevenueOpening",
            "deferredRevenueClosing", "restrictedCash",
        }
        for row in self.disclosures:
            with self.subTest(disclosure=row["id"]):
                self.assertTrue(row["name"].strip())
                self.assertRegex(row["fiscalYear"], r"^\d{4}-\d{4}$")
                self.assertTrue({str(value) for value in row["firstNationIds"]}.issubset(band_ids))
                self.assertNotIn("status", row)
                self.assertNotIn("estimatedCost", row)
                self.assertTrue(row.get("sourceReferences"))
                self.assertTrue(row.get("sources"))
                for source in row["sources"]:
                    self.assertTrue(source["url"].startswith("https://"))
                self.assertTrue(set(row.get("amounts", {})).issubset(allowed_amounts))
                for value in row.get("amounts", {}).values():
                    self.assertIsInstance(value, (int, float))
                    self.assertGreaterEqual(value, 0)

    def test_big_river_audited_project_regression(self):
        rows = {
            row["name"]: row
            for row in self.disclosures
            if str(row["firstNationIds"][0]) == "404" and row["fiscalYear"] == "2024-2025"
        }
        self.assertIn("2020 Housing Renovations", rows)
        self.assertEqual(rows["Drainage Project"]["amounts"]["fundingReceived"], 1_500_000)
        self.assertEqual(rows["Sewage Pumping Station and Lagoon"]["amounts"]["fundingReceived"], 2_630_000)
        self.assertEqual(rows["Community Connectivity"]["amounts"]["deferredRevenueClosing"], 150_000)
        self.assertNotIn("status", rows["New School Project"])

    def test_audit_research_leads_cannot_be_public_projects(self):
        research = json.loads((ROOT / "project-research-leads.json").read_text(encoding="utf-8"))
        self.assertNotIn("auditResearchLeads", self.payload)
        self.assertEqual(research.get("leadCount"), len(research.get("auditResearchLeads", [])))
        for lead in research.get("auditResearchLeads", []):
            with self.subTest(lead=lead.get("id")):
                self.assertFalse(lead.get("publishable", False))
                self.assertEqual(lead.get("researchStatus"), "pending_external_verification")
                self.assertTrue(lead.get("sourceDocument", {}).get("url"))
                self.assertTrue(lead.get("sourceReferences"))

    def test_unverified_candidates_are_source_linked_and_clearly_caveated(self):
        band_ids = {str(band["id"]) for band in self.bands}
        ids = [project["id"] for project in self.unverified]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertGreaterEqual(len(self.unverified), 10)
        forbidden_fields = {
            "status", "statusAsOf", "estimatedCost", "funding", "startDate",
            "completionDate", "expectedCompletionDate", "unitsCapacity",
        }
        for project in self.unverified:
            with self.subTest(project=project["id"]):
                self.assertTrue(project["name"].strip())
                self.assertTrue(project["discussionSummary"].strip())
                self.assertTrue(project["signalType"].strip())
                self.assertTrue(project["whyUnverified"].strip())
                self.assertRegex(project["lastSeenAt"], r"^\d{4}-\d{2}-\d{2}$")
                self.assertTrue({str(value) for value in project["firstNationIds"]}.issubset(band_ids))
                self.assertFalse(forbidden_fields.intersection(project))
                self.assertTrue(project["sources"])
                for source in project["sources"]:
                    self.assertTrue(source["url"].startswith("https://"))
                    self.assertRegex(source["publishedAt"], r"^\d{4}-\d{2}-\d{2}$")

    def test_unverified_policy_excludes_unsafe_rumours(self):
        policy = self.payload["unverifiedPolicy"]
        self.assertEqual(policy["label"], "Unverified Projects & Community Discussion")
        exclusions = " ".join(policy["exclusions"]).lower()
        self.assertIn("anonymous", exclusions)
        self.assertIn("private", exclusions)


if __name__ == "__main__":
    unittest.main()
