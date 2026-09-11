"""Source-first Alberta ingestion using OpenBand's shared schemas and parsers.

Public downloads are cached; source failures never become 'not posted'.
Run --discover, then --parse (resumable), then python -m tools.audit_alberta.
No paid parser calls.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import unicodedata
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lxml import html
import scraper
from tools.contact_scraper import parse_isc_profile
from tools.member_count_scraper import parse_population_page

CACHE = ROOT / '.openband-ocr' / 'alberta'
BASE = 'https://services.sac-isc.gc.ca/fnp/main/Search/'
COUNT_SOURCE = 'https://www.alberta.ca/first-nations-relations'
TREATY_SOURCE = 'https://www.sac-isc.gc.ca/eng/1595274954300/1595274980122'
ROSTER_PATH = ROOT / 'alberta-nations.json'
PARSER_REVISION = 'alberta-20260911-v4'

def now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def read(path, default=None):
    return json.loads(Path(path).read_text(encoding='utf-8')) if Path(path).exists() else default

def write(path, value):
    path = Path(path)
    # Existing OneDrive-backed data files may reject replace/rename even when
    # writes are allowed. Match the repository's other builders; parser results
    # are independently checkpointed per document before updating shared files.
    payload = (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    for attempt in range(6):
        try:
            with path.open('r+b' if path.exists() else 'wb') as handle:
                old_size = path.stat().st_size
                handle.write(payload)
                # Keep JSON readable even if a synced-file lock denies shrink.
                if old_size > len(payload):
                    handle.write(b'\n' * (old_size - len(payload)))
                handle.truncate(len(payload))
            return
        except PermissionError:
            if attempt == 5:
                raise
            time.sleep(.25 * (attempt + 1))

def normalized_name(value):
    value = unicodedata.normalize('NFKD', str(value).replace('ł', 'l').replace('Ł', 'L')).casefold()
    return re.sub(r'[^a-z0-9]+', ' ', value).strip()

def canonical_url(url):
    parts = urlsplit(url)
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path,
                      urlencode(sorted((k, v) for k, values in parse_qs(parts.query).items() for v in values)), ''))

def download(url, refresh=False):
    CACHE.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(canonical_url(url).encode()).hexdigest()
    path = CACHE / key
    if path.exists() and not refresh:
        return path.read_bytes()
    request = Request(canonical_url(url), headers={'User-Agent': 'OpenBand/2.0 public records research (+https://openband.ca)'})
    with urlopen(request, timeout=35) as response:
        payload = response.read(45 * 1024 * 1024)
    path.write_bytes(payload)
    return payload

def page_url(page, band_id):
    return f'{BASE}{page}.aspx?BAND_NUMBER={band_id}&lang=eng'

def tree(payload):
    return html.fromstring(payload.decode('utf-8-sig'))

def page_text(payload):
    return ' '.join(' '.join(tree(payload).xpath('//main//text()')).split())

def field(document, suffix):
    values = document.xpath(f'//*[@id="plcMain_{suffix}"]')
    return ' '.join(values[0].text_content().split()) if values else None

def verify_page(payload, band_id):
    text = page_text(payload)
    match = re.search(r'\bNumber\s+(\d+)\b', text)
    if not match or int(match[1]) != int(band_id):
        raise ValueError(f'ISC profile identity not confirmed for {band_id}')
    return text

def parse_filings(payload, band_id):
    verify_page(payload, band_id)
    parser = scraper.FilingParser()
    parser.feed(payload.decode('utf-8-sig'))
    filings, seen = [], set()
    for row in parser.rows:
        year, title, received = (row[i]['text'] for i in range(3))
        if not re.fullmatch(r'20\d{2}-20\d{2}', year):
            continue
        start, end = map(int, year.split('-'))
        if end != start + 1 or not 2014 <= start <= 2025:
            continue
        href = row[1]['href']
        if not href or received.lower() in ('not yet posted', '', '-', 'n/a'):
            continue  # Availability gaps are recorded in the audit, never invented PDFs.
        url = urljoin(BASE, href)
        query = {key.upper(): val for key, val in parse_qs(urlsplit(url).query).items()}
        source_band = query.get('BAND_NUMBER_FF', query.get('BAND_NUMBER', [str(band_id)]))[0]
        if str(source_band) != str(band_id):
            raise ValueError(f'Wrong band in document link: {source_band} != {band_id}')
        source_year = query.get('FY', [year])[0]
        if source_year != year:
            raise ValueError(f'Wrong fiscal year in document link: {source_year} != {year}')
        source_type = query.get('DOC', [title])[0]
        if normalized_name(source_type) != normalized_name(title):
            raise ValueError(f'Wrong document type in link: {source_type} != {title}')
        key = (year, normalized_name(title), canonical_url(url))
        if key in seen:
            continue
        seen.add(key)
        filings.append({'year': year, 'docType': title, 'documentTitle': f'{title} — {year}',
                        'date': received, 'href': url, 'posted': True, 'people': [],
                        'parse_status': 'pending', 'sourceOrganization': 'Indigenous Services Canada',
                        'sourceListingUrl': page_url('FederalFundingMain', band_id),
                        'sourceBandNumber': int(band_id), 'verificationStatus': 'official_listing',
                        'retrievedAt': now()})
    return filings

def discover_one(seed, refresh=False):
    band = dict(seed)
    band_id = seed.get('iscBandNumber', seed['id'])
    band['sources'] = list(seed.get('sources', []))
    errors = []
    for kind, page in [('profile', 'FNMain'), ('population', 'FNRegPopulation'),
                       ('geography', 'FNGeography'), ('reserves', 'FNReserves'),
                       ('leadership', 'FNGovernance'), ('filings', 'FederalFundingMain')]:
        if seed.get('sharedIscIdentity'):
            continue  # Do not attribute Saddle Lake totals or leadership to Whitefish Lake 128.
        url = page_url(page, band_id)
        try:
            payload = download(url, refresh)
            text = verify_page(payload, band_id)
            doc = tree(payload)
            band['sources'].append({'field': kind, 'url': url, 'retrievedAt': now()})
            if kind == 'profile':
                contact = parse_isc_profile(payload.decode('utf-8').encode('utf-8'), url)
                # lxml defaults to Latin-1 for byte input without a charset declaration.
                official = re.search(r'Official Name (.+?) (?:Phonetic Spelling|Number)', text)
                band['officialName'] = official[1] if official and '\ufffd' not in official[1] else seed['name']
                band['aliases'] = sorted(set(seed.get('aliases', []) + [band['officialName']]) - {band['name']})
                band['website'] = contact['website_url']
                band['contact'] = contact
                council = doc.xpath('//*[@id="plcMain_hlTCName"]')
                band['tribalCouncil'] = council[0].text_content().strip() if council else None
            elif kind == 'population':
                band['population'] = {**parse_population_page(payload.decode('utf-8')), 'sourceUrl': url}
                rows = [[ ' '.join(c.text_content().split()) for c in tr.xpath('./td')] for tr in doc.xpath('//tr')]
                own = [int(r[1].replace(',', '')) for r in rows if len(r) >= 2 and re.fullmatch(r'Registered (?:Males|Females) On Own Reserve', r[0], re.I) and re.fullmatch(r'[\d,]+', r[1])]
                band['population']['onOwnReserve'] = sum(own) if len(own) == 2 else None
            elif kind == 'geography':
                match = re.search(r'Most Populated Site (.+?) The allocation', text)
                band['mainReserve'] = match[1] if match else None
            elif kind == 'reserves':
                band['reserves'] = [{'number': cells[0], 'name': cells[1], 'location': cells[2], 'hectares': cells[3]}
                                    for tr in doc.xpath('//tr')
                                    if len(cells := [' '.join(c.text_content().split()) for c in tr.xpath('./td')]) == 4
                                    and cells[0].isdigit()]
            elif kind == 'leadership':
                band['leadership'] = {'sourceUrl': url, 'retrievedAt': now(), 'officials': []}
                for tr in doc.xpath('//tr'):
                    cells = [' '.join(c.text_content().split()) for c in tr.xpath('./td')]
                    if len(cells) == 5 and cells[0].lower() in ('chief', 'councillor'):
                        band['leadership']['officials'].append(dict(zip(['position', 'surname', 'givenName', 'appointmentDate', 'expiryDate'], cells)))
            else:
                band['filings'] = parse_filings(payload, band_id)
                band['discoveryStatus'] = 'checked'
        except Exception as error:
            errors.append({'kind': kind, 'url': url, 'error': f'{type(error).__name__}: {error}'})
    band['sourceErrors'] = errors
    band['sources'] = list({(s['field'], s['url']): s for s in band['sources']}.values())
    band['scraped'] = now()
    print(f"{band['id']} {band['name']}: {len(band.get('filings', []))} documents; {len(errors)} source errors", flush=True)
    return band

def discover(refresh=False):
    registry = read(ROSTER_PATH)
    data = read(ROOT / 'data.json')
    by_id = {str(b['id']): b for b in data['bands']}
    with ThreadPoolExecutor(max_workers=4) as pool:
        found = list(pool.map(lambda seed: discover_one(seed, refresh), registry['nations']))
    for band in found:
        existing = by_id.get(str(band['id']))
        if existing:
            old = {canonical_url(f['href']): f for f in existing.get('filings', []) if f.get('href')}
            incoming = band.pop('filings', [])
            for filing in incoming:
                key = canonical_url(filing['href'])
                if key not in old:
                    old[key] = filing
                else:
                    old[key].update({k: v for k, v in filing.items() if k in ('retrievedAt', 'date', 'sourceListingUrl')})
            band['filings'] = list(old.values())
            existing.update(band)
        else:
            band.setdefault('filings', [])
            data['bands'].append(band)
    data['generated'] = now()
    write(ROOT / 'data.json', data)
    integrate_profiles(data, found)

def integrate_profiles(data, bands):
    members = read(ROOT / 'member-counts.json')
    contacts = read(ROOT / 'contacts-data.json')
    maps = read(ROOT / 'map-data.json')
    locations = read(ROOT / 'tools/alberta-source-cache/isc-locations.json', {'features': []})
    location_by_id = {str(f['properties']['BAND_NUMBER']): f for f in locations['features']}
    for band in bands:
        bid = str(band['id'])
        if band.get('population'):
            p = band['population']
            members['bands'][bid] = {**p, 'name': band['name'], 'sourceName': 'Indigenous Services Canada', 'lastChecked': now()[:10]}
        if band.get('contact'):
            contacts['contacts'] = [c for c in contacts['contacts'] if str(c['nation_id']) != bid]
            contacts['contacts'].append({'nation_id': band['id'], 'nation_name': band['name'], **band['contact'],
                                         'office_email': None, 'source_url': page_url('FNMain', band['iscBandNumber']),
                                         'last_verified': now()[:10]})
        location = location_by_id.get(bid)
        if location:
            lon, lat = location['geometry']['coordinates']
            maps['communities'] = [c for c in maps['communities'] if str(c['id']) != bid]
            maps['communities'].append({'id': band['id'], 'name': band['name'], 'province': 'AB',
                                       'latitude': lat, 'longitude': lon, 'treaty': band.get('treaty'),
                                       'tribalCouncil': band.get('tribalCouncil'),
                                       'tribalCouncilSourceUrl': page_url('FNMain', band['iscBandNumber']),
                                       'reserveOwnerNames': [band['officialName']]})
    for filename, value in [('member-counts.json', members), ('contacts-data.json', contacts), ('map-data.json', maps)]:
        write(ROOT / filename, value)

def document_identity(pages, band, filing):
    """Check the report cover, independently of ISC's URL and listing."""
    cover = normalized_name(' '.join(pages[:4]))
    names = [band['name'], band.get('officialName', '')] + band.get('aliases', [])
    identity = any(normalized_name(n) in cover for n in names if len(normalized_name(n)) >= 5)
    year = int(filing['year'].split('-')[1])
    dates = re.findall(r'(?:march\s+31\s*,?\s*|31\s+march\s*,?\s*)(20\d{2})', ' '.join(pages[:4]), re.I)
    reasons = []
    if not identity:
        reasons.append('Nation identity not confirmed in document cover; manual review required')
    if not dates or int(dates[0]) != year:
        reasons.append('Fiscal year end not confirmed in document cover; manual review required')
    return reasons

def parse_one(task):
    band, filing, ocr = task
    from tools import capital_parser
    import run_scraper
    import pdfplumber
    update, summary = {'parserRevision': PARSER_REVISION}, None
    try:
        payload = download(filing['href'])
        if not payload.lstrip().startswith(b'%PDF-'):
            raise ValueError('Source did not return a PDF')
        update.update({'sha256': hashlib.sha256(payload).hexdigest(), 'byteSize': len(payload),
                       'verificationStatus': 'pdf_retrieved', 'lastChecked': now(), 'httpStatus': 200})
        # PDFium avoids spending minutes decoding complex vector graphics.
        # The accounting and remuneration interpretation still uses the shared parsers.
        try:
            import pypdfium2
            with pypdfium2.PdfDocument(payload) as pdf:
                pages = []
                for page in pdf:
                    textpage = page.get_textpage()
                    try:
                        pages.append(textpage.get_text_range().replace('\r', ''))
                    finally:
                        textpage.close()
                    page.close()
        except ImportError:
            with pdfplumber.open(io.BytesIO(payload)) as pdf:
                pages = [p.extract_text(x_tolerance=1, y_tolerance=3) or '' for p in pdf.pages]
        issues = document_identity(pages, band, filing)
        if ocr:
            # OCR the cover and statements once, then use those same pages for
            # independent identity checks and the existing accounting parsers.
            recognized = run_scraper.local_ocr.ocr_pdf_bytes(payload)
            update['ocrStatus'] = recognized.get('status')
            ocr_pages = recognized.get('pages', [])
            if ocr_pages:
                if issues:
                    issues = document_identity(ocr_pages, band, filing)
                pages = [native if len(native.strip()) > 80 else scanned
                         for native, scanned in zip(pages, ocr_pages)] + pages[len(ocr_pages):]
        update['documentChecks'] = {'identityAndYearConfirmed': not issues, 'warnings': issues}
        if capital_parser.is_audited_statement(filing):
            summary = capital_parser.parse_page_texts(pages, filing['href'], filing['year'])
            if not summary.get('publishable') and ocr and ocr_pages:
                alternative = capital_parser.parse_page_texts(ocr_pages, filing['href'], filing['year'])
                if alternative.get('publishable'):
                    summary = alternative
            if issues:
                summary.update({'publishable': False, 'parseStatus': 'manual_review', 'confidence': 'low'})
                summary['warnings'] = list(dict.fromkeys(summary.get('warnings', []) + issues))
            summary['sha256'] = update['sha256']
            update['parse_status'] = summary['parseStatus']
            update['warnings'] = summary.get('warnings', [])
        elif 'remuneration' in filing['docType'].lower():
            run_scraper.scraper.fetch_url = lambda *args, **kwargs: payload
            run_scraper.openai_fallback_enabled = lambda: False
            if not ocr:
                run_scraper.local_ocr.ocr_pdf_bytes = lambda *a, **kw: {'pages': [], 'status': 'deferred', 'warnings': ['OCR deferred; rerun with --ocr or review original PDF']}
            people = run_scraper._extract_people_from_text_pages(pages)
            result = run_scraper.parser_quality.apply_validation_metadata({'people': people, 'parse_status': 'ok_pdf_text' if people else 'manual_review', 'warnings': []})
            if not people:
                result.update({'manual_review_required': True, 'warnings': ['No reliable text rows; requires OCR or source review']})
            if issues or result.get('manual_review_required'):
                result.update({'people': [], 'parse_status': 'manual_review', 'manual_review_required': True})
                result['warnings'] = list(dict.fromkeys(result.get('warnings', []) + issues))
            update.update(result)
        if summary and summary.get('publishable') or update.get('people'):
            update['verificationStatus'] = 'automated_validated'
    except Exception as error:
        update.update({'parse_status': 'error', 'verificationStatus': 'retrieval_or_parse_error',
                       'warnings': [f'{type(error).__name__}: {error}'], 'lastChecked': now()})
    return str(band['id']), filing['href'], update, summary

def bounded_parse(task):
    """A pathological PDF must not stall the rest of the province's queue."""
    band, filing, ocr = task
    key = hashlib.sha256((str(band['id']) + filing['href']).encode()).hexdigest()
    source, output = CACHE / f'{key}.task.json', CACHE / f'{key}.result.json'
    if output.exists() and not ocr:
        cached = read(output)
        if cached[2].get('parse_status') != 'error' and cached[2].get('parserRevision') == PARSER_REVISION:
            return cached
    write(source, task)
    try:
        subprocess.run([sys.executable, str(Path(__file__).resolve()), '--task', str(source), '--result', str(output)],
                       timeout=180 if ocr else 45, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return read(output)
    except Exception as error:
        return str(band['id']), filing['href'], {'parse_status': 'manual_review', 'warnings': [f'Bounded extraction stopped: {type(error).__name__}'], 'lastChecked': now(), 'verificationStatus': 'parse_timeout_or_error'}, None

def parse_documents(limit=0, workers=3, ocr=False, retry=False, reparse=False, document_type='all'):
    from tools.capital_parser import save_summary
    data, capital = read(ROOT / 'data.json'), read(ROOT / 'capital-data.json')
    tasks = [(band, filing, ocr) for band in data['bands'] if band.get('province') == 'AB'
             for filing in band.get('filings', []) if filing.get('posted') and filing.get('href')
             and (document_type=='all' or document_type in filing['docType'].lower())
             and (reparse or not filing.get('lastChecked') or retry and filing.get('verificationStatus') != 'automated_validated')]
    tasks.sort(key=lambda t: (t[1]['year'], t[0]['name']), reverse=True)
    if limit:
        tasks = tasks[:limit]
    by_id = {str(b['id']): b for b in data['bands']}
    filings = {(str(b['id']), f['href']): f for b in data['bands'] for f in b.get('filings', []) if f.get('href')}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending = [pool.submit(bounded_parse, task) for task in tasks]
        for index, future in enumerate(as_completed(pending), 1):
            bid, url, update, summary = future.result()
            filing = filings[bid, url]
            filing.update(update)
            if summary:
                existing = capital.get('bands', {}).get(bid, {}).get('years', {}).get(filing['year'])
                if reparse or not existing or not existing.get('publishable') or summary.get('publishable'):
                    save_summary(capital, by_id[bid], filing, summary)
            print(f"[{index}/{len(tasks)}] {bid} {filing['year']} {filing['docType']}: {filing['parse_status']}", flush=True)
            if index % 50 == 0:
                write(ROOT / 'data.json', data)
                write(ROOT / 'capital-data.json', capital)
    write(ROOT / 'data.json', data)
    write(ROOT / 'capital-data.json', capital)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--discover', action='store_true')
    parser.add_argument('--refresh-roster', action='store_true')
    parser.add_argument('--refresh', action='store_true')
    parser.add_argument('--parse', action='store_true')
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--workers', type=int, default=3)
    parser.add_argument('--ocr', action='store_true')
    parser.add_argument('--retry', action='store_true')
    parser.add_argument('--reparse', action='store_true', help='Revalidate all selected documents with the current parser revision')
    parser.add_argument('--document-type', choices=['all', 'audited', 'remuneration'], default='all')
    parser.add_argument('--task')
    parser.add_argument('--result')
    args = parser.parse_args()
    if args.task:
        write(args.result, parse_one(read(args.task)))
        return
    if args.refresh_roster:
        from tools.refresh_alberta_roster import build
        build(refresh=True)
    if args.discover:
        discover(args.refresh)
    if args.parse:
        parse_documents(args.limit, args.workers, args.ocr, args.retry, args.reparse, args.document_type)

if __name__ == '__main__':
    main()
