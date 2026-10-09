"""Download public geometry evidence without changing the map dataset."""
import json
import sys
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
from tools.build_map_data import RESERVE_LAND_URL

if __name__ == '__main__':
    parameters = {
        'where': "CPC_CODE IN ('SK','AB')", 'outFields': 'ADMIN_LAND_ID,SHORT_NAME,ENAME,CPC_CODE,FIRST_NATIONS',
        'returnGeometry': 'true', 'outSR': '4326', 'f': 'geojson',
        'resultRecordCount': '2000'}
    if '--full' not in sys.argv:
        parameters['maxAllowableOffset'] = '0.001'
    url = RESERVE_LAND_URL + '?' + urlencode(parameters)
    with urlopen(url, timeout=40) as response:
        data = json.load(response)
    name = 'reserve-full.geojson' if '--full' in sys.argv else 'reserve-audit.geojson'
    Path('.openband-ocr',name).write_text(json.dumps(data), encoding='utf-8')
    print('features', len(data.get('features', [])), 'error', data.get('error'))
    print('AB owners', sorted({owner.strip() for feature in data.get('features', [])
                              if feature['properties']['CPC_CODE'] == 'AB'
                              for owner in (feature['properties']['FIRST_NATIONS'] or '').split(',')}))
