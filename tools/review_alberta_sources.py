"""Recheck Alberta website identity and collect reviewable logo candidates.

Does not change shared site data or approve logos without visual review.
"""
from concurrent.futures import ThreadPoolExecutor
from tools.ingest_alberta import ROOT, read, write, now
from tools.enrich_alberta import SITES
from tools.collect_first_nation_logos import (
    request_bytes, LogoHTMLParser, official_site_matches, collect_band,
)


def inspect(band):
    site = SITES.get(band['id'], band.get('website'))
    if site and site.startswith('http:'):
        site = 'https:' + site[5:]
    row = {'id': band['id'], 'name': band['name'], 'website': site,
           'checkedAt': now(), 'websiteVerified': False, 'errors': []}
    if not site:
        return row
    try:
        payload, content_type, final = request_bytes(site)
        parser = LogoHTMLParser(final)
        parser.feed(payload.decode('utf-8', errors='replace'))
        if content_type not in ('text/html', 'application/xhtml+xml'):
            raise ValueError('Website did not return HTML')
        names = [band['name'], band.get('officialName', '')] + band.get('aliases', [])
        if not any(official_site_matches(parser, n) for n in names if n):
            raise ValueError('Website identity not confirmed')
        row.update({'website': final, 'websiteVerified': True, 'candidates': parser.candidates})
        if not band.get('logo_verified'):
            try:
                row['logo'], row['logoAttempts'] = collect_band(band, final, 'Official First Nation website')
                row['logoVisualReview'] = 'pending'
            except Exception as error:
                row['errors'].append({'kind': 'logo', 'url': final, 'error': str(error)})
    except Exception as error:
        row['errors'].append({'kind': 'website', 'url': site, 'error': str(error)})
    print(f"{band['id']} {band['name']}: website {row['websiteVerified']}; logo candidate {bool(row.get('logo'))}", flush=True)
    return row


def main():
    bands = [b for b in read(ROOT/'data.json')['bands'] if b.get('province') == 'AB']
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(inspect, bands))
    write(ROOT/'alberta-source-review.json', {'generated': now(), 'nations': rows})


if __name__ == '__main__':
    main()
