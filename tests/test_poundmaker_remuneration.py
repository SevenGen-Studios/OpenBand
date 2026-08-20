import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PoundmakerRemunerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data = json.loads((ROOT / "data.json").read_text(encoding="utf-8"))
        cls.band = next(band for band in data["bands"] if band["name"] == "Poundmaker Cree Nation")
        cls.filings = {
            filing["year"]: filing
            for filing in cls.band["filings"]
            if "remuneration" in filing.get("docType", "").lower()
        }

    def test_official_schedule_totals_reconcile_for_every_repaired_year(self):
        expected_totals = {
            "2013-2014": 328829,
            "2014-2015": 315645,
            "2015-2016": 344274,
            "2016-2017": 368150,
            "2017-2018": 390259,
            "2018-2019": 384505,
            "2019-2020": 478856,
            "2020-2021": 1099860,
            "2021-2022": 867581,
            "2022-2023": 1079726,
            "2023-2024": 819925,
            "2024-2025": 687507,
        }
        for year, expected_total in expected_totals.items():
            with self.subTest(year=year):
                filing = self.filings[year]
                self.assertEqual("manual_from_official_pdf", filing["parse_status"])
                self.assertEqual(expected_total, sum(person["total"] for person in filing["people"]))
                for person in filing["people"]:
                    components = sum(
                        person.get(key) or 0
                        for key in ("remuneration", "travel", "expenses", "creditCard", "otherPayments")
                    )
                    self.assertEqual(person["total"], components, person["name"])

    def test_latest_schedule_columns_are_not_swapped_or_polluted_by_notes(self):
        people = self.filings["2024-2025"]["people"]
        self.assertEqual(7, len(people))
        self.assertFalse(any(person["name"].lower().startswith(("in the", "during the")) for person in people))
        chief = next(person for person in people if person["role"] == "Chief")
        self.assertEqual(33079, chief["travel"])
        self.assertEqual(50000, chief["otherPayments"])

    def test_business_and_contracted_services_are_included_in_totals(self):
        darwin = next(
            person
            for person in self.filings["2020-2021"]["people"]
            if person["name"] == "Darwin Kasokeo"
        )
        self.assertEqual(374575, darwin["otherPayments"])
        self.assertEqual(447234, darwin["total"])


if __name__ == "__main__":
    unittest.main()
