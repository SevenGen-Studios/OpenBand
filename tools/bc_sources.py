"""Cached, rate-limited public non-financial BC source retrieval."""
import hashlib,json,os,tempfile,time,http.cookiejar,gzip,threading
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import Request,build_opener,HTTPCookieProcessor
ROOT=Path(__file__).resolve().parents[1]
CACHE=ROOT/'tools/bc-source-cache'
UA='OpenBand/2.0 public community profile research (+https://openband.ca)'
ROSTER='https://services.sac-isc.gc.ca/fnp/main/Search/SearchFN.aspx?lang=eng'
PROVINCE='https://www2.gov.bc.ca/gov/content/environment/natural-resource-stewardship/consulting-with-first-nations/first-nations-negotiations/first-nations-a-z-listing'
BCAFN='https://www.bcafn.ca/first-nations-bc/interactive-map'
TREATIES='https://www.sac-isc.gc.ca/eng/1595274954300/1595274980122'
OPENER=build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
_last=0
_rate_lock=threading.Lock()

def now():return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
def read(path):
 path=Path(path)
 return json.loads(path.read_text(encoding='utf-8') if path.exists() else gzip.decompress(path.with_suffix(path.suffix+'.gz').read_bytes()).decode('utf-8'))
def atomic_write(path,value):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=path.parent,delete=False) as f:
  json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n');f.flush();os.fsync(f.fileno());tmp=f.name
 try:os.replace(tmp,path)
 finally:
  if Path(tmp).exists():Path(tmp).unlink()
def fetch(url,refresh=False,data=None,timeout=30):
 global _last
 if any(x in url.lower() for x in ('federalfunding','displaybinary','financial','remuneration','.pdf')):raise ValueError('Financial/PDF retrieval is excluded from Phase 2')
 CACHE.mkdir(parents=True,exist_ok=True);key=hashlib.sha256((url+'|'+str(data)).encode()).hexdigest();path=CACHE/(key+'.html');meta=path.with_suffix('.json')
 if (path.exists() or path.with_suffix(path.suffix+".gz").exists()) and meta.exists() and not refresh:
  payload=path.read_bytes() if path.exists() else gzip.decompress(path.with_suffix(path.suffix+".gz").read_bytes())
  if hashlib.sha256(payload).hexdigest()!=read(meta)['sha256']:raise ValueError('Cached source digest mismatch')
  return payload,read(meta)
 with _rate_lock:
  time.sleep(max(0,.7-(time.monotonic()-_last)));_last=time.monotonic()
 try:
  with OPENER.open(Request(url,data=data,headers={'User-Agent':UA}),timeout=timeout) as response:
   payload=response.read(30*1024*1024);final=response.url
  metadata={'url':url,'finalUrl':final,'retrievedAt':now(),'sha256':hashlib.sha256(payload).hexdigest(),'bytes':len(payload),'status':'retrieved','cacheFile':path.name}
  path.write_bytes(payload);atomic_write(meta,metadata);return payload,metadata
 except Exception as e:
  atomic_write(CACHE/(key+'.error.json'),{'url':url,'retrievedAt':now(),'error':str(e),'status':'inaccessible'})
  raise

def fetch_initial(refresh=False):
 from lxml import html
 from urllib.parse import urlencode
 from tools.build_map_data import LOCATION_URL,RELATION_URL
 for url in (PROVINCE,BCAFN,TREATIES,'https://bctreaty.ca/'):
  try:p,m=fetch(url,refresh);print(url,len(p),flush=True)
  except Exception as e:print(url,type(e).__name__,str(e),flush=True)
 p,m=fetch(ROSTER,refresh);doc=html.fromstring(p)
 fields={i.get('name'):i.get('value','') for i in doc.xpath('//input[@type="hidden"]') if i.get('name','').startswith('__')}
 fields.update({'ctl00$plcMain$ddlProvince':'BC','ctl00$plcMain$ddlRegion':'','ctl00$plcMain$txtName':'','ctl00$plcMain$txtNumber':'','ctl00$plcMain$btnSearch':'Search'})
 p,m=fetch(ROSTER,refresh,data=urlencode(fields).encode());atomic_write(CACHE/'roster-source.json',m);(CACHE/'roster.html').write_bytes(p);print('ISC roster',len(p),flush=True)
 for label,url in [('locations',LOCATION_URL),('relations',RELATION_URL)]:
  p,m=fetch(url+'?'+urlencode({'where':'1=1','outFields':'*','returnGeometry':'true' if label=='locations' else 'false','outSR':'4326','f':'geojson' if label=='locations' else 'json','resultRecordCount':'2000'}),refresh);atomic_write(CACHE/(label+'-source.json'),m);(CACHE/(label+'.json')).write_bytes(p);print(label,len(p),flush=True)

def prepare_inputs():
 from lxml import html
 from html import unescape
 from urllib.parse import parse_qs,urlsplit,urljoin
 from tools.ingest_alberta import page_url
 p,meta=fetch(PROVINCE);v=json.loads(html.fromstring(p.decode('utf-8-sig')).xpath('//script[@id="__NEXT_DATA__"]')[0].text)
 strings=[]
 def walk(x):
  if isinstance(x,dict):
   for k,value in x.items():
    if k=='value' and isinstance(value,str) and ('&lt;table' in value or '<table' in value):strings.append(unescape(value))
    else:walk(value)
  elif isinstance(x,list):
   for value in x:walk(value)
 walk(v['props']['pageProps']['data']['results'][0]['components'])
 doc=html.fromstring('<div>'+''.join(strings)+'</div>');rows=[]
 for tr in doc.xpath('//tr'):
  cells=[' '.join(c.text_content().split()) for c in tr.xpath('./td')];links=tr.xpath('./td[1]//a/@href')
  if len(cells)==4 and links and not links[0].startswith('#'):rows.append({'name':cells[0],'region':cells[2],'location':cells[1],'memberOf':cells[3],'url':urljoin(PROVINCE,links[0])})
 atomic_write(CACHE/'provincial-candidates.json',rows)
 p,meta=fetch(BCAFN);atomic_write(CACHE/'bcafn-embedded.json',json.loads(html.fromstring(p.decode()).xpath('//script[@type="application/json"]')[0].text))
 source=read(CACHE/'roster-source.json');doc=html.fromstring((CACHE/'roster.html').read_bytes().decode('utf-8-sig'));seeds=[]
 for tr in doc.xpath('//tr'):
  cells=[' '.join(c.text_content().split()) for c in tr.xpath('./td')]
  if len(cells)!=3 or not cells[0].isdigit():continue
  number=int(cells[0]);links=tr.xpath('.//a/@href')
  if not links or any(parse_qs(urlsplit(u).query).get('BAND_NUMBER')!=[str(number)] for u in links):raise ValueError('ISC row/link identity mismatch')
  seeds.append({'id':number,'iscBandNumber':number,'name':cells[1],'officialName':cells[1],'aliases':[],'province':'BC','filings':[],'verificationStatus':'verified_isc_identity','verifiedAt':source['retrievedAt'],'sources':[{'field':'identity',**source},{'field':'profile','url':page_url('FNMain',number)}]})
 if not seeds or len(seeds)!=len({b['id'] for b in seeds}):raise ValueError('Incomplete/duplicate ISC identity response')
 atomic_write(CACHE/'isc-seeds.json',{'nations':seeds})

if __name__=='__main__':
 import argparse
 parser=argparse.ArgumentParser();parser.add_argument('--refresh',action='store_true');args=parser.parse_args();fetch_initial(args.refresh);prepare_inputs()

