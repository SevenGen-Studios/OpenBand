"""Build a validated display snapshot from the original ISC reserve geometry.

Requires optional shapely (pip install -r requirements-maps.txt). The source
geometry is retained in the ignored cache; ownership, parcel IDs and reported
areas are never inferred. This display layer is not a legal survey.
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
from tools.build_map_data import RESERVE_LAND_URL


def build():
    from shapely.geometry import shape, mapping, MultiPolygon
    from shapely import make_valid
    parameters = {'where': "CPC_CODE IN ('SK','AB')", 'outFields': 'ADMIN_LAND_ID,SHORT_NAME,ENAME,CPC_CODE,FIRST_NATIONS',
                  'returnGeometry':'true','outSR':'4326','f':'geojson','resultRecordCount':'2000'}
    url = RESERVE_LAND_URL+'?'+urlencode(parameters)
    with urlopen(url,timeout=45) as response:
        payload=response.read()
    source=json.loads(payload)
    if source.get('type') != 'FeatureCollection' or source.get('exceededTransferLimit') or not source.get('features'):
        raise ValueError('Complete non-empty ISC GeoJSON is required')
    report={'sourceUrl':url,'retrievedAt':datetime.now(timezone.utc).isoformat(),
            'sourceSha256':hashlib.sha256(payload).hexdigest(),'sourceFeatureCount':len(source['features']),
            'displaySimplificationDegrees':0.0001,'repairs':[], 'blocked':[]}
    features=[]
    for feature in source['features']:
        geometry=shape(feature['geometry'])
        if not geometry.is_valid:
            repaired=make_valid(geometry)
            if repaired.geom_type=='GeometryCollection':
                polygons=[part for part in repaired.geoms if part.geom_type=='Polygon']
                polygons += [p for part in repaired.geoms if part.geom_type=='MultiPolygon' for p in part.geoms]
                repaired=MultiPolygon(polygons)
            change=abs(repaired.area-geometry.area)/max(abs(geometry.area),1e-20)
            details={'reserveId':feature['properties']['ADMIN_LAND_ID'],
                     'name':feature['properties']['SHORT_NAME'], 'relativePlanarAreaChange':change,
                     'method':'GEOS make_valid linework; preserve source parcel and ownership'}
            if not repaired.is_valid or repaired.is_empty or repaired.geom_type not in {'Polygon','MultiPolygon'} or change>0.001:
                report['blocked'].append(details)
                continue
            report['repairs'].append(details)
            geometry=repaired
        simplified=geometry.simplify(0.0001,preserve_topology=True)
        if not simplified.is_valid or simplified.is_empty:
            raise ValueError('Invalid display geometry after topology-preserving simplification')
        features.append(dict(feature,geometry=mapping(simplified)))
    if report['blocked']:
        raise ValueError('Source geometries need manual review; existing snapshot was preserved')
    result={'type':'FeatureCollection','sourceUrl':url,'retrievedAt':report['retrievedAt'],
            'displayOnly':True,'features':features}
    output=Path('public/reserve-boundaries.geojson')
    output.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    report['outputSha256']=hashlib.sha256(output.read_bytes()).hexdigest()
    report['featureCount']=len(features)
    Path('reserve-boundary-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'Validated {len(features)} display parcels; repaired {len(report["repairs"])} source geometries; {output.stat().st_size} bytes')


if __name__=='__main__':
    build()
