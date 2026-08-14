import unittest

from tools.build_map_data import (
    build_map_data,
    council_display_name,
    parse_relation_text,
    reserve_feature_area_hectares,
    reserve_land_totals,
)


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

    def test_fsin_fills_documented_isc_relationship_gaps(self):
        bands = [
            {"id": 340, "name": "Little Pine First Nation", "treaty": "Treaty 6"},
            {"id": 363, "name": "Ochapowace First Nation", "treaty": "Treaty 4"},
            {"id": 365, "name": "White Bear First Nations", "treaty": "Treaty 4"},
        ]
        locations = {"features": [{
            "geometry": {"coordinates": [-104.0, 51.0]},
            "properties": {"BAND_NUMBER": band["id"], "BAND_NAME": band["name"]},
        } for band in bands]}
        result = build_map_data(bands, locations, {"features": []})
        rows = {row["id"]: row for row in result["communities"]}
        self.assertEqual(rows[340]["tribalCouncil"], "Battlefords Agency Tribal Chiefs (BATC)")
        self.assertEqual(rows[363]["tribalCouncil"], "South East Treaty 4 Tribal Council")
        self.assertEqual(rows[365]["tribalCouncil"], "South East Treaty 4 Tribal Council")
        self.assertEqual(rows[363]["tribalCouncilSourceUrl"], "https://www.fsin.ca/sask-fn-listings")

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
        self.assertEqual(council_display_name("BATTLEFORDS AGENCY TRIBAL CHIEFS INC"), "Battlefords Agency Tribal Chiefs (BATC)")
        self.assertEqual(council_display_name("NORTHWEST PROFESSIONAL SERVICES CORP."), "Battlefords Agency Tribal Chiefs (BATC)")
        self.assertIsNone(council_display_name(None))

    def test_projected_reserve_geometry_converts_square_metres_to_hectares(self):
        feature = {"geometry": {"rings": [[[0, 0], [100, 0], [100, 100], [0, 100], [0, 0]]]}}
        self.assertEqual(reserve_feature_area_hectares(feature), 1)

    def test_reserve_totals_attribute_shared_land_to_each_named_nation(self):
        bands = [
            {"id": 378, "name": "Carry the Kettle Nakoda Nation"},
            {"id": 366, "name": "Cote First Nation"},
        ]
        reserve_lands = {"features": [{
            "attributes": {"FIRST_NATIONS": "Carry The Kettle, Cote First Nation 366"},
            "geometry": {"rings": [[[0, 0], [200, 0], [200, 100], [0, 100], [0, 0]]]},
        }]}
        totals = reserve_land_totals(bands, reserve_lands)
        self.assertEqual(totals[378], {"hectares": 2, "parcelCount": 1})
        self.assertEqual(totals[366], {"hectares": 2, "parcelCount": 1})


if __name__ == "__main__":
    unittest.main()
