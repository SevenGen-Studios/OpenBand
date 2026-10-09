"""Associate ISC polygons by official reserve number, with explicit owner fallback.

Does not derive area from simplified geographic geometry or copy shared identities.
Supply the saved ISC GeoJSON query response; the source URL stays on every record.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from tools.build_map_data import boundary_ids, RESERVE_LAND_URL


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('geojson', type=Path)
    args = parser.parse_args()
    data = json.loads(Path('data.json').read_text(encoding='utf-8'))
    map_data = json.loads(Path('map-data.json').read_text(encoding='utf-8'))
    geometry = json.loads(args.geojson.read_text(encoding='utf-8'))
    if geometry.get('type') != 'FeatureCollection' or geometry.get('exceededTransferLimit'):
        raise ValueError('Complete ISC GeoJSON is required')
    bands = {str(band['id']): band for band in data['bands']}
    for record in map_data['communities']:
        record['reserveLandIds'] = boundary_ids(bands[str(record['id'])], record, geometry['features'])
        record['reserveBoundarySourceUrl'] = RESERVE_LAND_URL.rsplit('/query', 1)[0]
        record['reserveBoundaryCheckedAt'] = datetime.now(timezone.utc).isoformat()
    Path('map-data.json').write_text(json.dumps(map_data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print('Boundary associations:', sum(bool(row['reserveLandIds']) for row in map_data['communities']))


if __name__ == '__main__':
    main()
