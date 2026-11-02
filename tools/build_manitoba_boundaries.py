"""Append verified Manitoba reserve display polygons while preserving SK/AB features."""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request,urlopen
from tools.ingest_manitoba import ROOT,SOURCE_CACHE,dataset_lock,safe_write
from tools.ingest_alberta import now
from tools.manitoba_baseline import digest
from tools.build_map_data import RESERVE_LAND_URL,boundary_ids
from tools.build_reserve_boundaries import validated_display_features

def protected_features(features):
    return {str(f['properties']['ADMIN_LAND_ID']):digest(f) for f in features if f['properties'].get('CPC_CODE') in ('SK','AB')}

def fetch():
    params={'where':"CPC_CODE='MB'",'outFields':'ADMIN_LAND_ID,SHORT_NAME,ENAME,CPC_CODE,FIRST_NATIONS','returnGeometry':'true','outSR':'4326','f':'geojson','resultRecordCount':'2000'}
    url=RESERVE_LAND_URL+'?'+urlencode(params)
    with urlopen(Request(url,headers={'User-Agent':'OpenBand/2.0 public Manitoba reserve geometry research'}),timeout=60) as response:payload=response.read(45*1024*1024)
    data=json.loads(payload)
    if data.get('type')!='FeatureCollection' or data.get('exceededTransferLimit') or not data.get('features'):raise ValueError('Complete non-empty Manitoba geometry required')
    if any(f['properties'].get('CPC_CODE')!='MB' for f in data['features']):raise ValueError('Unexpected province in Manitoba geometry source')
    (SOURCE_CACHE/'reserve-boundaries-original.geojson').write_bytes(payload)
    safe_write(SOURCE_CACHE/'reserve-boundaries-source.json',{'sourceUrl':url,'retrievedAt':now(),'sha256':hashlib.sha256(payload).hexdigest(),'sourceFeatureCount':len(data['features'])})
    print('Fetched',len(data['features']),'Manitoba source parcels',flush=True)

def build():
    original=ROOT/'public/reserve-boundaries.geojson'
    source=json.loads((SOURCE_CACHE/'reserve-boundaries-original.geojson').read_text())
    provenance=json.loads((SOURCE_CACHE/'reserve-boundaries-source.json').read_text())
    if hashlib.sha256((SOURCE_CACHE/'reserve-boundaries-original.geojson').read_bytes()).hexdigest()!=provenance['sha256']:raise ValueError('Source geometry digest differs from saved provenance')
    report={**provenance,'displaySimplificationDegrees':0.0001,'repairs':[],'blocked':[]}
    added=validated_display_features(source,report)
    with dataset_lock():
        current=json.loads(original.read_text());baseline_path=SOURCE_CACHE/'boundary-baseline.json'
        protected=protected_features(current['features'])
        if baseline_path.exists():
            if protected!=json.loads(baseline_path.read_text())['features']:raise ValueError('Protected SK/AB geometry changed')
        else:safe_write(baseline_path,{'originalFileSha256':hashlib.sha256(original.read_bytes()).hexdigest(),'features':protected})
        preserved=[f for f in current['features'] if f['properties'].get('CPC_CODE')!='MB']
        combined=preserved+added
        if protected_features(combined)!=protected:raise ValueError('Expansion would alter protected geometry')
        ids=[str(f['properties']['ADMIN_LAND_ID']) for f in combined]
        if len(ids)!=len(set(ids)):raise ValueError('Duplicate administrative parcel IDs')
        result={**current,'features':combined,'sourceUrls':list(dict.fromkeys([current['sourceUrl'],provenance['sourceUrl']])),'manitobaExpandedAt':now()}
        temporary=original.with_suffix('.geojson.tmp');temporary.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n');temporary.replace(original)
        data=json.loads((ROOT/'data.json').read_text());maps=json.loads((ROOT/'map-data.json').read_text());bands={str(b['id']):b for b in data['bands'] if b.get('province')=='MB'}
        for record in maps['communities']:
            band=bands.get(str(record['id']))
            if band:
                record.update(reserveLandIds=boundary_ids(band,record,source['features']),reserveBoundarySourceUrl=RESERVE_LAND_URL.rsplit('/query',1)[0],reserveBoundaryCheckedAt=provenance['retrievedAt'])
        safe_write(ROOT/'map-data.json',maps)
        report.update(displayFeatureCount=len(added),protectedSKABFeaturesUnchanged=True,manitobaCommunitiesWithBoundaries=sum(bool(r.get('reserveLandIds')) for r in maps['communities'] if str(r['id']) in bands))
    safe_write(ROOT/'manitoba-boundary-validation.json',report)
    print('Validated',len(added),'Manitoba display parcels;',report['manitobaCommunitiesWithBoundaries'],'Nation associations; original SK/AB geometries unchanged',flush=True)
    return report
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--refresh',action='store_true');p.add_argument('--fetch-only',action='store_true');args=p.parse_args()
    if args.refresh:fetch()
    if not args.fetch_only:build()
