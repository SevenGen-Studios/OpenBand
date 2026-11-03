"""Refresh source snapshots only; rerun the audits and review changes afterward."""
import urllib.request, urllib.parse, http.cookiejar, json, hashlib
from pathlib import Path
from datetime import datetime, timezone
from lxml import html
root=Path('research/band-numbers/2026-11-03')
url='https://services.sac-isc.gc.ca/fnp/main/Search/SearchFN.aspx?lang=eng'
manifest={}
for province in ['SK','AB','MB']:
 opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
 opener.addheaders=[('User-Agent','OpenBand/2.0 public roster reconciliation')]
 doc=html.fromstring(opener.open(url,timeout=45).read())
 fields={i.get('name'):i.get('value','') for i in doc.xpath('//input[@type="hidden"]') if i.get('name','').startswith('__')}
 fields.update({'ctl00$plcMain$ddlProvince':province,'ctl00$plcMain$ddlRegion':'','ctl00$plcMain$txtName':'','ctl00$plcMain$txtNumber':'','ctl00$plcMain$btnSearch':'Search'})
 payload=opener.open(urllib.request.Request(url,data=urllib.parse.urlencode(fields).encode()),timeout=60).read()
 filename=f'isc-roster-{province.lower()}.html';(root/filename).write_bytes(payload)
 rows=[]
 for tr in html.fromstring(payload).xpath('//tr'):
  cells=[' '.join(c.text_content().split()) for c in tr.xpath('./td')]
  if len(cells)==3 and cells[0].isdigit():
   bid=int(cells[0]);links=tr.xpath('.//a/@href');assert links and all(urllib.parse.parse_qs(urllib.parse.urlsplit(link).query).get('BAND_NUMBER')==[str(bid)] for link in links)
   rows.append({'iscBandNumber':bid,'officialName':cells[1],'province':province})
 assert rows and len({r['iscBandNumber'] for r in rows})==len(rows)
 manifest[province]={'url':url,'requestProvince':province,'retrievedAt':datetime.now(timezone.utc).isoformat(),'sha256':hashlib.sha256(payload).hexdigest(),'nations':rows}
 print(province,len(rows),flush=True)
(root/'provincial-rosters.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
for key,u in [('fsin-listings','https://www.fsin.ca/sask-fn-listings'),('treaty-annuities','https://www.sac-isc.gc.ca/eng/1595274954300/1595274980122')]:
 payload=urllib.request.urlopen(u,timeout=60).read();(root/(key+'.html')).write_bytes(payload);print(key,len(payload),flush=True)
