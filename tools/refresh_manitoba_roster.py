"""Reproduce 63 Manitoba ISC identities; join treaties and points by band number."""
import hashlib
import http.cookiejar
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path
from lxml import html
from tools.ingest_manitoba import ROOT,SOURCE_CACHE,safe_write
from tools.ingest_alberta import now,page_url
from tools.build_map_data import LOCATION_URL
COUNT_SOURCE='https://www.isc-sac.gc.ca/eng/1626886719453/1626886859809'
TREATY_SOURCE='https://isc-sac.gc.ca/eng/1595274954300/1595274980122'
ROSTER_SOURCE='https://services.sac-isc.gc.ca/fnp/main/Search/SearchFN.aspx?lang=eng'
AMC_SOURCE='https://manitobachiefs.com/about/first-nation-members-of-amc/'

def refresh_sources():
    SOURCE_CACHE.mkdir(exist_ok=True)
    opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    opener.addheaders=[('User-Agent','OpenBand/2.0 public records research (+https://openband.ca)')]
    payload=opener.open(ROSTER_SOURCE,timeout=35).read();doc=html.fromstring(payload)
    fields={i.get('name'):i.get('value','') for i in doc.xpath('//input[@type="hidden"]') if i.get('name','').startswith('__')}
    fields.update({'ctl00$plcMain$ddlProvince':'MB','ctl00$plcMain$ddlRegion':'','ctl00$plcMain$txtName':'','ctl00$plcMain$txtNumber':'','ctl00$plcMain$btnSearch':'Search'})
    sources={'isc-roster.html':ROSTER_SOURCE,'province.html':COUNT_SOURCE,'treaties.html':TREATY_SOURCE,'amc.html':AMC_SOURCE,'isc-locations.json':LOCATION_URL+'?where=1%3D1&outFields=*&returnGeometry=true&outSR=4326&f=geojson'}
    manifest={}
    for name,url in sources.items():
        request=urllib.request.Request(url,data=urllib.parse.urlencode(fields).encode()) if name=='isc-roster.html' else url
        payload=opener.open(request,timeout=60).read()
        (SOURCE_CACHE/name).write_bytes(payload)
        manifest[name]={'url':url,'retrievedAt':now(),'sha256':hashlib.sha256(payload).hexdigest(),'requestProvince':'MB' if name=='isc-roster.html' else None}
    safe_write(SOURCE_CACHE/'sources.json',manifest)

def build(refresh=False):
    if refresh:refresh_sources()
    def document(name):return html.fromstring((SOURCE_CACHE/name).read_bytes().decode('utf-8-sig'))
    roster=document('isc-roster.html');nations=[];membership={}
    for table in document('treaties.html').xpath('//table'):
        match=re.search(r'Treaty No\.\s*(\d+)', ' '.join(table.text_content().split()))
        if not match:continue
        for tr in table.xpath('.//tr'):
            cells=[' '.join(c.text_content().split()) for c in tr.xpath('./td|./th')]
            if len(cells)==3 and cells[0].isdigit() and cells[2]=='MB':membership[int(cells[0])]={'treaty':f'Treaty {match[1]}','alias':cells[1]}
    locations=json.loads((SOURCE_CACHE/'isc-locations.json').read_text())
    if locations.get('exceededTransferLimit'):raise ValueError('Incomplete ISC location source')
    points={int(f['properties']['BAND_NUMBER']):f for f in locations['features']}
    # Non-signatory status is explicitly listed by ISC, not inferred from absence.
    non_signatory={'Birdtail Sioux','Sioux Valley','Canupawakpa','Dakota Tipi','Dakota Plains'}
    count_text=' '.join(document('province.html').text_content().split())
    if '63 First Nations' not in count_text:raise ValueError('Recheck provincial count source')
    for tr in roster.xpath('//tr'):
        cells=[' '.join(c.text_content().split()) for c in tr.xpath('./td')]
        if len(cells)!=3 or not cells[0].isdigit():continue
        bid=int(cells[0]);name=cells[1];sources=[{'field':'identity','url':ROSTER_SOURCE,'retrievedAt':now()},{'field':'profile','url':page_url('FNMain',bid)}]
        # Confirm the official row's link, independent of its display number.
        links=tr.xpath('.//a/@href')
        if not links or any(urllib.parse.parse_qs(urllib.parse.urlsplit(link).query).get('BAND_NUMBER')!=[str(bid)] for link in links):raise ValueError('ISC row link identity mismatch')
        member=membership.get(bid);aliases=set();point=points.get(bid)
        if member:aliases.add(member['alias']);sources.append({'field':'treaty','url':TREATY_SOURCE})
        status='verified_numbered_treaty' if member else 'not_verified'
        if not member and any(name.startswith(n) for n in non_signatory):status='non_signatory';sources.append({'field':'treatyStatus','url':COUNT_SOURCE})
        nation={'id':bid,'iscBandNumber':bid,'name':name,'officialName':name,'aliases':[],'province':'MB','treaty':member['treaty'] if member else None,'treatyVerificationStatus':status,'sources':sources,'verifiedAt':now(),'filings':[]}
        if point:
            aliases.add(point['properties']['BAND_NAME'])
            nation['location']={'longitude':point['geometry']['coordinates'][0],'latitude':point['geometry']['coordinates'][1],'sourceUrl':LOCATION_URL,'retrievedAt':now()}
            sources.append({'field':'location','url':LOCATION_URL})
        nation['aliases']=sorted(aliases-{name})
        nations.append(nation)
    ids=[n['id'] for n in nations]
    if len(nations)!=63 or len(set(ids))!=63:raise ValueError(f'Expected 63 unique ISC identities; got {len(ids)}')
    existing=json.loads((ROOT/'data.json').read_text())
    if any(str(b['id']) in {str(i) for i in ids} and b.get('province')!='MB' for b in existing['bands']):raise ValueError('Protected province identity collision')
    result={'schemaVersion':1,'verifiedAt':now(),'expectedNationCount':63,'countSource':COUNT_SOURCE,'rosterSource':ROSTER_SOURCE,'iscIdentityCount':63,'secondaryReference':AMC_SOURCE,'limitations':['AMC alternate names require band-number-backed reconciliation before addition. Unavailable profile fields remain unverified.'],'nations':sorted(nations,key=lambda n:n['name'])}
    safe_write(ROOT/'manitoba-nations.json',result)
    print(f'Verified {len(nations)} unique Manitoba ISC identities; {sum(bool(n["treaty"]) for n in nations)} treaty memberships; {sum(bool(n.get("location")) for n in nations)} official locations',flush=True)
    return result
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--refresh',action='store_true');a=p.parse_args();build(a.refresh)
