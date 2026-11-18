"""Append validated BC reserve geometry without changing existing province features."""
from urllib.parse import urlencode
from tools.bc_sources import *
from tools.build_map_data import RESERVE_LAND_URL

def retrieve():
 features=[];sources=[];offset=0
 while True:
  params={'where':"CPC_CODE='BC'",'outFields':'ADMIN_LAND_ID,SHORT_NAME,ENAME,CPC_CODE,FIRST_NATIONS','returnGeometry':'true','outSR':'4326','f':'geojson','resultRecordCount':'200','resultOffset':str(offset),'orderByFields':'ADMIN_LAND_ID'}
  url=RESERVE_LAND_URL+'?'+urlencode(params);p,m=fetch(url);v=json.loads(p)
  if v.get('type')!='FeatureCollection' or 'error'in v:raise ValueError('Invalid geometry response')
  batch=v.get('features',[])
  if any(f['properties']['CPC_CODE']!='BC' for f in batch):raise ValueError('Unexpected province geometry')
  features.extend(batch);sources.append(m);print('BC source parcels',len(features),flush=True)
  if not v.get('exceededTransferLimit') and len(batch)<200:break
  if not batch:break
  offset+=len(batch)
  if offset>5000:raise ValueError('Unexpected geometry pagination size')
 ids=[str(f['properties']['ADMIN_LAND_ID']) for f in features]
 if len(ids)!=len(set(ids)) or not ids:raise ValueError('Repeated/empty geometry pagination')
 atomic_write(CACHE/'bc-boundaries-source.json',{'type':'FeatureCollection','features':features,'sources':sources});return features
if __name__=='__main__':retrieve()
