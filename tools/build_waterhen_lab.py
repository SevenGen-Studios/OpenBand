"""Download a bounded, reproducible OSM/ISC snapshot for the isolated map lab."""
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / 'first-nations/waterhen-lake-first-nation/map/data'
ISC = 'https://data.sac-isc.gc.ca/geomatics/rest/services/ILRS_PRD/ERIP_E_NRCan/MapServer/26/query'
OSM = 'https://overpass-api.de/api/interpreter'

def building_height(tags):
    """Return a display height while preserving whether OSM supplied it."""
    raw_height = tags.get('height', '')
    match = re.search(r'\d+(?:\.\d+)?', raw_height.replace(',', '.'))
    if match:
        value = float(match.group())
        if 'ft' in raw_height.lower() or "'" in raw_height:
            value *= 0.3048
        if 1 <= value <= 150:
            return round(value, 2), 'OSM height tag'
    try:
        levels = float(tags.get('building:levels', ''))
        if 0 < levels <= 50:
            return round(levels * 3, 2), 'OSM building:levels tag (3 m per level)'
    except ValueError:
        pass
    return 4, 'Illustrative default'

def close_ring(coords):
    return coords if coords and coords[0] == coords[-1] else coords + coords[:1]

def assemble_rings(members, role):
    """Join Overpass relation-member ways into closed GeoJSON rings."""
    segments = []
    for member in members:
        if member.get('type') != 'way' or member.get('role', 'outer') != role:
            continue
        coords = [[point['lon'], point['lat']] for point in member.get('geometry', [])]
        if len(coords) >= 2:
            segments.append(coords)
    rings = []
    while segments:
        ring = segments.pop(0)
        while ring[0] != ring[-1]:
            joined = False
            for index, segment in enumerate(segments):
                if ring[-1] == segment[0]:
                    ring.extend(segment[1:])
                elif ring[-1] == segment[-1]:
                    ring.extend(reversed(segment[:-1]))
                elif ring[0] == segment[-1]:
                    ring = segment[:-1] + ring
                elif ring[0] == segment[0]:
                    ring = list(reversed(segment[1:])) + ring
                else:
                    continue
                segments.pop(index)
                joined = True
                break
            if not joined:
                break
        if len(ring) >= 4 and ring[0] == ring[-1]:
            rings.append(ring)
    return rings

def request(url, params):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(params).encode(), headers={'User-Agent': 'OpenBand Map Lab (https://openband.ca)'})
    with urllib.request.urlopen(req, timeout=120) as response:
        return json.load(response)

def main():
    reserve = request(ISC, {'where': "ADMIN_LAND_ID='06603'", 'outFields': 'ADMIN_LAND_ID,SHORT_NAME,FIRST_NATIONS', 'returnGeometry': 'true', 'outSR': '4326', 'f': 'geojson'})
    if len(reserve.get('features', [])) != 1:
        raise ValueError('Expected the Waterhen reserve polygon')
    bbox = '54.30,-108.49,54.54,-108.26'
    query = f'[out:json][timeout:90];(way[building]({bbox});way[highway]({bbox});way[waterway]({bbox});way[natural=water]({bbox});relation[type=multipolygon][natural=water]({bbox});relation[type=multipolygon][water]({bbox}););out geom;'
    raw = request(OSM, {'data': query})
    if raw.get('remark'):
        raise ValueError(raw['remark'])
    poi_query = f'[out:json][timeout:60];(nwr[amenity]({bbox});nwr[shop]({bbox});nwr[office]({bbox});nwr[tourism]({bbox});nwr[leisure]({bbox});nwr[place]({bbox}););out center tags;'
    poi_raw = request(OSM, {'data': poi_query})
    if poi_raw.get('remark'):
        raise ValueError(poi_raw['remark'])
    layers = {name: [] for name in ('buildings', 'roads', 'water', 'poi')}
    seen_water_ways = {
        member.get('ref')
        for relation in raw.get('elements', []) if relation.get('type') == 'relation'
        for member in relation.get('members', []) if member.get('type') == 'way'
    }
    for row in raw.get('elements', []):
        tags = row.get('tags', {})
        if row.get('type') == 'relation':
            outers = assemble_rings(row.get('members', []), 'outer')
            inners = assemble_rings(row.get('members', []), 'inner')
            if not outers:
                continue
            geometry = {'type': 'MultiPolygon', 'coordinates': [[[point for point in outer]] + inners for outer in outers]}
            properties = {**tags, 'osmId': row['id'], 'osmType': 'relation', 'sourceUrl': f"https://www.openstreetmap.org/relation/{row['id']}"}
            layers['water'].append({'type': 'Feature', 'id': f"relation/{row['id']}", 'geometry': geometry, 'properties': properties})
            continue
        coords = [[p['lon'], p['lat']] for p in row.get('geometry', [])]
        if len(coords) < 2:
            continue
        polygon = len(coords) >= 4 and coords[0] == coords[-1]
        layer = 'buildings' if 'building' in tags else 'roads' if 'highway' in tags else 'water'
        if layer == 'water' and row['id'] in seen_water_ways:
            continue
        if layer == 'buildings' and not polygon:
            continue
        geometry = {'type': 'Polygon', 'coordinates': [coords]} if polygon and layer != 'roads' else {'type': 'LineString', 'coordinates': coords}
        properties = {**tags, 'osmId': row['id'], 'osmType': 'way', 'sourceUrl': f"https://www.openstreetmap.org/way/{row['id']}"}
        if layer == 'buildings':
            properties['renderHeight'], properties['heightSource'] = building_height(tags)
        layers[layer].append({'type': 'Feature', 'id': f"way/{row['id']}", 'geometry': geometry, 'properties': properties})
    for row in poi_raw.get('elements', []):
        tags = row.get('tags', {})
        point = row if row.get('type') == 'node' else row.get('center', {})
        if not tags.get('name') or 'lat' not in point or 'lon' not in point:
            continue
        osm_type = row['type']
        layers['poi'].append({'type': 'Feature', 'id': f"{osm_type}/{row['id']}", 'geometry': {'type': 'Point', 'coordinates': [point['lon'], point['lat']]}, 'properties': {**tags, 'osmId': row['id'], 'osmType': osm_type, 'sourceUrl': f"https://www.openstreetmap.org/{osm_type}/{row['id']}"}})
    OUT.mkdir(parents=True, exist_ok=True)
    datasets = {'reserve': reserve, **{key: {'type': 'FeatureCollection', 'features': value} for key, value in layers.items()}}
    for name, value in datasets.items():
        (OUT / f'{name}.geojson').write_text(json.dumps(value, separators=(',', ':')) + '\n')
    sourced_heights = sum(feature['properties']['heightSource'] != 'Illustrative default' for feature in layers['buildings'])
    metadata = {'bandId': 402, 'name': 'Waterhen Lake First Nation', 'retrievedAt': datetime.now(timezone.utc).isoformat(), 'iscSource': ISC, 'osmSource': OSM, 'query': query, 'poiQuery': poi_query, 'counts': {**{key: len(value) for key, value in layers.items()}, 'buildingsWithSourcedHeight': sourced_heights}, 'coverage': 'Bounding-box snapshot includes surrounding land; OSM completeness is unknown. Water multipolygon relations are assembled when their member ways form closed rings. Named places appear only when explicitly tagged in OSM.', 'heightPolicy': 'OSM height tags are used when valid; building:levels uses 3 metres per level. All other buildings use an illustrative 4 metre display height.'}
    (OUT / 'metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
    print(json.dumps(metadata['counts']))

if __name__ == '__main__':
    main()
