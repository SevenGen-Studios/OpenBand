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

    def test_schema_and_project_ids(self):
        self.assertEqual(self.payload["schemaVersion"], 1)
        self.assertRegex(self.payload["generatedAt"], r"^\d{4}-\d{2}-\d{2}$")
        ids = [project["id"] for project in self.projects]
        self.assertEqual(len(ids), len(set(ids)))

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


if __name__ == "__main__":
    unittest.main()
