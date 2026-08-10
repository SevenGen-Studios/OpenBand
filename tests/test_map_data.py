import unittest

from tools.build_map_data import build_map_data, council_display_name, parse_relation_text


class MapDataTests(unittest.TestCase):
    def test_official_records_join_by_band_number(self):
        bands = [{"id": 378, "name": "Carry the Kettle Nakoda Nation", "treaty": "Treaty 4"}]
        locations = {"features": [{
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [-103.4674, 50.3549]},
            "properties": {"BAND_NUMBER": 378, "BAND_NAME": "Carry The Kettle"},
        }]}
        relations = {"features": [{"attributes": {
            "BAND_NUMBER": 378,
            "BAND_NAME": "Carry The Kettle",
            "TRIBAL_COUNCIL_NUMBER": 1041,
            "TRIBAL_COUNCIL_NAME": "FILE HILLS QU'APPELLE TRIBAL COUNCIL INC.",
        }}]}
        result = build_map_data(bands, locations, relations)
        self.assertEqual(result["communityCount"], 1)
        self.assertFalse(result["missingLocations"])
        row = result["communities"][0]
        self.assertEqual(row["name"], "Carry the Kettle Nakoda Nation")
        self.assertEqual(row["tribalCouncil"], "File Hills Qu'Appelle Tribal Council")
        self.assertEqual(row["tribalCouncilSourceLabel"], "FILE HILLS QU'APPELLE TRIBAL COUNCIL INC.")

    def test_arcgis_text_fallback_preserves_source_label(self):
        source = """
BAND_NUMBER: 371
BAND_NAME: Muskoday First Nation
TRIBAL_COUNCIL_NUMBER: 1051.0
TRIBAL_COUNCIL_NAME: Saskatoon Tribal Council
"""
        parsed = parse_relation_text(source)
        self.assertEqual(parsed["features"][0]["attributes"]["BAND_NUMBER"], 371)
        self.assertEqual(parsed["features"][0]["attributes"]["TRIBAL_COUNCIL_NAME"], "Saskatoon Tribal Council")

    def test_known_corporate_labels_have_public_display_names(self):
        self.assertEqual(council_display_name("MLTC PROGRAM SERVICES INC."), "Meadow Lake Tribal Council")
        self.assertEqual(council_display_name("PADC MANAGEMENT COMPANY LTD."), "Prince Albert Grand Council")
        self.assertIsNone(council_display_name(None))


if __name__ == "__main__":
    unittest.main()
