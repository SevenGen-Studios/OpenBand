import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAP_ROOT = ROOT / 'first-nations' / 'waterhen-lake-first-nation' / 'map'
SPEC = importlib.util.spec_from_file_location(
    'build_waterhen_lab', ROOT / 'tools' / 'build_waterhen_lab.py'
)
LAB = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LAB)


class WaterhenMapLabTests(unittest.TestCase):
    def test_building_height_preserves_explicit_height(self):
        self.assertEqual(LAB.building_height({'height': '12 m'}), (12.0, 'OSM height tag'))

    def test_building_levels_are_clearly_derived(self):
        self.assertEqual(
            LAB.building_height({'building:levels': '2'}),
            (6.0, 'OSM building:levels tag (3 m per level)'),
        )

    def test_untagged_building_uses_disclosed_default(self):
        self.assertEqual(LAB.building_height({}), (4, 'Illustrative default'))

    def test_relation_segments_are_joined_into_ring(self):
        members = [
            {'type': 'way', 'role': 'outer', 'geometry': [{'lon': 0, 'lat': 0}, {'lon': 1, 'lat': 0}]},
            {'type': 'way', 'role': 'outer', 'geometry': [{'lon': 1, 'lat': 1}, {'lon': 0, 'lat': 0}]},
            {'type': 'way', 'role': 'outer', 'geometry': [{'lon': 1, 'lat': 0}, {'lon': 1, 'lat': 1}]},
        ]
        rings = LAB.assemble_rings(members, 'outer')
        self.assertEqual(len(rings), 1)
        self.assertEqual(rings[0][0], rings[0][-1])
        self.assertEqual({tuple(point) for point in rings[0]}, {(0, 0), (1, 0), (1, 1)})

    def test_snapshot_contains_relation_water_and_height_provenance(self):
        water = json.loads((MAP_ROOT / 'data/water.geojson').read_text())
        buildings = json.loads((MAP_ROOT / 'data/buildings.geojson').read_text())
        self.assertTrue(any(row['properties']['osmType'] == 'relation' for row in water['features']))
        self.assertTrue(all('heightSource' in row['properties'] for row in buildings['features']))

    def test_named_places_are_source_linked(self):
        places = json.loads((MAP_ROOT / 'data/poi.geojson').read_text())
        self.assertTrue(places['features'])
        self.assertTrue(all(row['properties'].get('name') for row in places['features']))
        self.assertTrue(all(row['properties'].get('sourceUrl', '').startswith('https://www.openstreetmap.org/') for row in places['features']))

    def test_community_camera_supports_a_useful_zoom_range(self):
        javascript = (MAP_ROOT / 'waterhen-map.js').read_text()
        self.assertIn('range:1950', javascript)
        self.assertIn('minimumZoomDistance=120', javascript)
        self.assertIn('maximumZoomDistance=30000', javascript)


if __name__ == '__main__':
    unittest.main()
