"""Reconcile the Alberta roster against ISC identities and treaty membership.

The reviewed count is 48 governments: 47 distinct ISC identities, plus the
separately administered Whitefish Lake #128 government (shared ISC 462).
Stoney 471 is an umbrella administration, not a fourth Stoney Nation.
Onion Lake remains one Saskatchewan profile with cross-border discovery.
"""
import re
from pathlib import Path
from tools.ingest_alberta import ROOT, read, write, tree, now, download, TREATY_SOURCE, COUNT_SOURCE

def build(refresh=False):
    if refresh:
        from tools.build_map_data import LOCATION_URL
        (ROOT/'tools/alberta-source-cache').mkdir(exist_ok=True)
        locations = download(LOCATION_URL+'?where=1%3D1&outFields=*&returnGeometry=true&outSR=4326&f=geojson', refresh=True)
        (ROOT/'tools/alberta-source-cache/isc-locations.json').write_bytes(locations)
        (ROOT/'tools/alberta-source-cache/treaties.html').write_bytes(download(TREATY_SOURCE, refresh=True))
    locations = read(ROOT / 'tools/alberta-source-cache/isc-locations.json')
    treaties = tree((ROOT / 'tools/alberta-source-cache/treaties.html').read_bytes())
    membership = {}
    for table in treaties.xpath('//table'):
        match = re.search(r'Treaty No\.\s*(\d+)', ' '.join(table.text_content().split()))
        if not match:
            continue
        for tr in table.xpath('.//tr'):
            cells = [' '.join(c.text_content().split()) for c in tr.xpath('./td|./th')]
            if len(cells) == 3 and cells[0].isdigit():
                membership[int(cells[0])] = {'treaty': f'Treaty {match[1]}', 'alias': cells[1], 'province': cells[2]}
    nations = []
    for f in locations['features']:
        bid, name = f['properties']['BAND_NUMBER'], f['properties']['BAND_NAME']
        member = membership.get(bid)
        if not member or member['province'] != 'AB' or bid == 471:
            continue
        nations.append({'id': bid, 'iscBandNumber': bid, 'name': name, 'officialName': name,
                        'aliases': [member['alias']] if member['alias'] != name else [], 'province': 'AB',
                        'treaty': member['treaty'], 'sources': [
                            {'field': 'identity', 'url': 'https://data.sac-isc.gc.ca/geomatics/rest/services/Donnees_Ouvertes-Open_Data/Premiere_Nation_First_Nation/FeatureServer/0'},
                            {'field': 'treaty', 'url': TREATY_SOURCE}]})
    # Peerless Trout and Lubicon need a separate membership source if absent
    # from the annuity list. Never assign their treaty from their location.
    located = {n['id'] for n in nations}
    missing = [f['properties'] for f in locations['features'] if 430 <= f['properties']['BAND_NUMBER'] <= 478 and f['properties']['BAND_NUMBER'] != 471 and f['properties']['BAND_NUMBER'] not in located]
    if missing:
        raise ValueError(f'Treaty membership needs verification: {missing}')
    nations.append({'id': 'ab-whitefish-lake-128', 'iscBandNumber': 462,
                    'name': 'Whitefish Lake First Nation #128', 'officialName': 'Whitefish Lake First Nation #128',
                    'aliases': ['Whitefish (Goodfish) Lake First Nation', 'Goodfish Lake'], 'province': 'AB',
                    'treaty': 'Treaty 6', 'sharedIscIdentity': True, 'relatedNationIds': [462],
                    'website': 'https://www.wfl128.ca/', 'mainReserve': 'WHITEFISH LAKE 128',
                    'identityNote': 'Administered separately from Saddle Lake, with shared ISC band number 462. Financial and population totals are not copied from the shared band profile.',
                    'sources': [
                        {'field': 'identity', 'url': 'https://publications.gc.ca/collections/collection_2014/aadnc-aandc/R2-141-2014-eng.pdf'},
                        {'field': 'website', 'url': 'https://www.wfl128.ca/'},
                        {'field': 'treaty', 'url': 'https://open.alberta.ca/dataset/baf3eeda-0f24-4268-aa72-7897f77ca912/resource/6ec6a1c7-c543-47d1-ab18-57a65836cf29/download/external-fn-contact-list-july-24-2019.pdf'}]})
    assert len(nations) == 48, len(nations)
    existing = {str(n['id']):n for n in read(ROOT/'alberta-nations.json',{'nations':[]})['nations']}
    for nation in nations:
        previous = existing.get(str(nation['id']), {})
        for field in ('name','aliases','website','identityNote','relatedDisclosureSources'):
            if field in previous:
                nation[field] = previous[field]
    write(ROOT / 'alberta-nations.json', {'schemaVersion': 1, 'verifiedAt': now(), 'expectedNationCount': 48,
                                         'countSource': COUNT_SOURCE, 'iscIdentityCount': 47,
                                         'excludedUmbrellaIds': [471], 'crossBorderNationIds': [344],
                                         'reconciliation': __doc__, 'nations': sorted(nations, key=lambda n: n['name'])})

if __name__ == '__main__':
    build()
