"""Reviewable official-site discovery and logo collection, without touching filings."""
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlsplit
from tools.ingest_alberta import ROOT, read, write, now, download, tree
from tools.collect_first_nation_logos import collect_band, unverified_record

# Public sources reviewed September 11, 2026. Each URL identifies its Nation.
SITES = {
    445: 'https://www.beaverfirstnation.com/', 451: 'https://www.duncansfirstnation.com/',
    440: 'https://enochnation.ca/', 465: 'https://www.froglake.ca/',
    469: 'https://heartlakefirstnation.com/', 466: 'https://www.kehewincree.ca/',
    476: 'https://loonriverfirstnation.ca/', 453: 'https://www.lubiconlakeband.ca/',
    478: 'https://www.ptfn.net/', 454: 'https://sawridgefirstnation.com/',
    455: 'https://www.sturgeonlake.ca/', 456: 'https://scfn.ca/',
    434: 'https://www.sunchildfirstnation.com/', 457: 'https://srfn.ca/',
    446: 'https://www.tallcree.ca/', 459: 'https://www.whitefishlake459.com/',
    477: 'https://www.slfn196.com/', 474: 'https://woodlandcree.ca/',
    433: 'https://www.chiniki.com/', 475: 'https://www.goodstoneynation.ca/',
}

def inspect(band):
    site = SITES.get(band['id'], band.get('website'))
    result = {'id': band['id'], 'website': site, 'checkedAt': now(), 'researchPages': [], 'candidateDocuments': [], 'errors': []}
    if not site or 'stoneynation.com' in site:
        result['logo'] = unverified_record(band, site, 'ISC-listed website', 'No distinct Nation logo source verified; shared Stoney marks are not assigned to individual Nations.')
        return result
    try:
        payload = download(site)
        doc = tree(payload)
        result['websiteVerified'] = True
        result['researchPages'].append({'url': site, 'status': 'retrieved'})
        links = []
        for a in doc.xpath('//a[@href]'):
            url = urljoin(site, a.get('href')).split('#')[0]
            text = a.text_content() + ' ' + url
            if urlsplit(url).netloc == urlsplit(site).netloc and re.search(r'economic|business|enterprise|financ|annual.report|publications', text, re.I) and url not in links:
                links.append(url)
        for url in links[:5]:
            try:
                body = download(url)
                result['researchPages'].append({'url': url, 'status': 'retrieved'})
                if body.lstrip().startswith(b'%PDF-'):
                    result['candidateDocuments'].append({'url': url, 'status': 'manual_review', 'reason': 'Official-site PDF; identity, type and year must be checked before indexing'})
                    continue
                page = tree(body)
                for a in page.xpath('//a[@href]'):
                    target = urljoin(url, a.get('href'))
                    if '.pdf' in target.lower() and re.search(r'financ|audit|remuneration|annual.report', a.text_content() + target, re.I):
                        result['candidateDocuments'].append({'url': target, 'sourcePage': url, 'status': 'manual_review'})
            except Exception as error:
                result['errors'].append({'url': url, 'error': str(error)})
    except Exception as error:
        result['errors'].append({'url': site, 'error': str(error)})
    try:
        logo, attempts = collect_band(band, site, 'Official First Nation website')
        # Collector provenance checks are followed by a visual review before merge.
        result['logo'] = logo
        result['logoAttempts'] = attempts
        result['logoVisualReview'] = 'pending'
    except Exception as error:
        result['logo'] = unverified_record(band, site, 'Official First Nation website', str(error))
    print(f"{band['id']} {band['name']}: logo {result['logo']['logo_status']}; {len(result['researchPages'])} official pages checked", flush=True)
    write(ROOT / '.openband-ocr' / f"alberta-enrichment-{band['id']}.json", result)
    return result

def main():
    bands = [b for b in read(ROOT / 'data.json')['bands'] if b.get('province') == 'AB']
    with ThreadPoolExecutor(max_workers=5) as pool:
        rows = list(pool.map(inspect, bands))
    write(ROOT / 'alberta-enrichment.json', {'generated': now(), 'nations': rows})

if __name__ == '__main__':
    main()
