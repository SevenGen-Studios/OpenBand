"""Source-linked, static financial records and explanatory pages.

Only existing publishable extractions get annual pages. Missing values remain
missing; neither the builder nor structured data infers financial figures.
"""
from __future__ import annotations
import hashlib
import html
import json
import math
from pathlib import Path
from urllib.parse import urlparse

ORIGIN = 'https://openband.ca'
PROVINCES = {'SK': 'Saskatchewan', 'AB': 'Alberta'}

def esc(value):
    return html.escape(str(value), quote=True)

def safe_url(value):
    try:
        return str(value) if urlparse(str(value)).scheme in {'https', 'http'} else ''
    except ValueError:
        return ''

def amount(value):
    # Data contains numeric CAD values. Never coerce unknown or missing to zero.
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None

def money(value):
    value = amount(value)
    return 'Not reported' if value is None else f'{"−" if value < 0 else ""}${abs(value):,.0f}'

def reliable_filing(filing):
    status = str(filing.get('parse_status') or '')
    return bool(filing.get('posted') and filing.get('people') and safe_url(filing.get('href'))
                and not filing.get('manual_review_required')
                and not status.startswith('manual_review')
                and status not in {'pending_manual_review', 'sanitized_no_valid_rows'}
                and filing.get('parse_confidence') not in {'low', 'manual_review_required'})

def financial_years(band, capital):
    years = {}
    for filing in band.get('filings', []):
        year = str(filing.get('year') or '')
        if 'remuneration' in str(filing.get('docType', '')).lower() and reliable_filing(filing):
            # Prefer manually reviewed records when duplicate documents exist.
            score = (filing.get('parse_confidence') == 'manual_reviewed', len(filing['people']))
            old = years.setdefault(year, {}).get('remuneration')
            if old is None or score > (old.get('parse_confidence') == 'manual_reviewed', len(old['people'])):
                years[year]['remuneration'] = filing
    for year, summary in capital.get('bands', {}).get(str(band['id']), {}).get('years', {}).items():
        if (summary.get('parseStatus') == 'parsed' and summary.get('publishable') is not False
                and safe_url(summary.get('sourceUrl')) and any(amount(summary.get(k)) is not None for k in ('totalRevenue', 'totalExpenses', 'annualSurplusDeficit', 'capitalAssets'))):
            years.setdefault(str(year), {})['financial'] = summary
    import re
    return {year: value for year, value in sorted(years.items(), reverse=True)
            if re.fullmatch(r'20\d{2}-20\d{2}', year) and int(year[5:]) == int(year[:4]) + 1}

def record_path(band, year, slugify):
    return f'/first-nations/{slugify(band["name"])}/financials/{year}/'

def source_link(url, label):
    url = safe_url(url)
    return f'<a href="{esc(url)}">{esc(label)}</a>' if url else ''

def financial_markup(summary, year):
    labels = [('totalRevenue', 'Total revenue'), ('totalExpenses', 'Total expenses'),
              ('annualSurplusDeficit', 'Annual surplus / deficit'), ('capitalAssets', 'Tangible capital assets'),
              ('cashInvestments', 'Cash and investments')]
    figures = ''.join(f'<div><dt>{label}</dt><dd>{money(summary.get(key))}</dd></div>' for key, label in labels if amount(summary.get(key)) is not None)
    return (f'<section><h2>Audited financial statement summary · {esc(year)}</h2>'
            '<p>Amounts in Canadian dollars, extracted from the published statement. A surplus is an accounting result; it is not the same as unrestricted cash.</p>'
            f'<dl class="record-metrics">{figures}</dl>'
            f'<p>{source_link(summary.get("sourceUrl"), "Review original audited financial statements (PDF)")}</p>'
            f'<p class="record-note">Extraction confidence: {esc(summary.get("confidence") or "Not specified")}. Verify figures and notes in the source document.</p></section>')

def travel_expenses(person):
    combined = amount(person.get('travelExpenses'))
    if combined is not None:
        return combined
    components = [amount(person.get(key)) for key in ('travel', 'expenses', 'creditCard')]
    disclosed = [value for value in components if value is not None]
    return sum(disclosed) if disclosed else None

def remuneration_markup(filing, year):
    rows = []
    for person in filing.get('people', []):
        if not str(person.get('name') or '').strip():
            continue
        # Keep remuneration separate; never add canonical expenses to their components.
        fields = [esc(person['name']), esc(person.get('role') or 'Not specified'),
                  esc(person['months']) if person.get('months') is not None else 'Not reported',
                  money(person.get('remuneration')), money(travel_expenses(person)),
                  money(person.get('otherPayments') if person.get('otherPayments') is not None else person.get('other'))]
        rows.append('<tr>' + ''.join(f'<td>{value}</td>' for value in fields) + '</tr>')
    return (f'<section><h2>Chief and Council remuneration and expenses · {esc(year)}</h2>'
            '<p>Historical payments for the stated fiscal year. These names do not identify current officeholders. Remuneration and other payments stay separate. Travel / expenses uses the stored combined amount when available; otherwise it sums the disclosed travel, expenses, and credit-card components. The combined amount is never added again to its components. Missing values are not zero.</p>'
            '<div class="record-table-wrap"><table><caption>Parsed remuneration schedule · amounts in Canadian dollars</caption><thead><tr>'
            '<th scope="col">Name</th><th scope="col">Position</th><th scope="col">Months</th><th scope="col">Remuneration</th><th scope="col">Travel / expenses</th><th scope="col">Other payments</th>'
            '</tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div>'
            f'<p>{source_link(filing.get("href"), "Review original remuneration and expenses schedule (PDF)")}</p></section>')

def breadcrumb(items):
    return '<nav class="record-breadcrumb" aria-label="Breadcrumb">' + ' <span aria-hidden="true">/</span> '.join(f'<a href="{esc(path)}">{esc(name)}</a>' for name, path in items) + '</nav>'

def shell(title, description, path, body, *, schema=None, breadcrumbs=None):
    graph = [{'@type': 'WebPage', '@id': ORIGIN + path + '#page', 'url': ORIGIN + path,
              'name': title, 'description': description, 'isPartOf': {'@id': ORIGIN + '/#website'},
              'publisher': {'@id': ORIGIN + '/#publisher'}},
             {'@type': 'WebSite', '@id': ORIGIN + '/#website', 'name': 'OpenBand', 'url': ORIGIN + '/'},
             {'@type': 'Organization', '@id': ORIGIN + '/#publisher', 'name': 'SevenGenStudios', 'url': ORIGIN + '/about/'}]
    if schema:
        graph.extend(schema)
    if breadcrumbs:
        graph.append({'@type': 'BreadcrumbList', 'itemListElement': [
            {'@type': 'ListItem', 'position': i, 'name': name, 'item': ORIGIN + url}
            for i, (name, url) in enumerate(breadcrumbs, 1)]})
    structured = json.dumps({'@context': 'https://schema.org', '@graph': graph}, ensure_ascii=False).replace('<', '\\u003c')
    return f'''<!doctype html><html lang="en-CA"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><meta name="description" content="{esc(description)}"><link rel="canonical" href="{ORIGIN}{esc(path)}">
<meta name="robots" content="index,follow,max-image-preview:large"><meta property="og:type" content="website"><meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(description)}"><meta property="og:url" content="{ORIGIN}{esc(path)}"><meta property="og:image" content="{ORIGIN}/assets/openband-social.png"><meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="/assets/favicon.svg" type="image/svg+xml"><link rel="stylesheet" href="/assets/records.css?v=20261011a"><script type="application/ld+json">{structured}</script></head>
<body><header class="record-header"><a href="/" class="record-brand">OpenBand</a><nav aria-label="Primary navigation"><a href="/first-nations/">First Nations</a><a href="/financials/">Financial records</a><a href="/methodology/">Methodology</a></nav></header>
<main class="record-main">{breadcrumb(breadcrumbs) if breadcrumbs else ''}{body}</main>
<footer class="record-footer"><a href="/about/">About OpenBand</a> · <a href="/methodology/">Sources and corrections</a><p>&copy; <span data-current-year>2026</span> OpenBand. All rights reserved. A product of SevenGenStudios.</p></footer>
<script>document.querySelector('[data-current-year]').textContent=new Date().getFullYear()</script><script src="/assets/analytics-config.js"></script><script src="/assets/analytics.js?v=20261011a" defer></script></body></html>'''

def annual_page(band, year, record, years, slugify):
    name, slug = band['name'], slugify(band['name'])
    path = record_path(band, year, slugify)
    topic = 'Financial Statements & Remuneration' if len(record) == 2 else 'Financial Statements' if 'financial' in record else 'Chief & Council Remuneration'
    title = f'{name} {topic} {year} | OpenBand'
    description = f'{name}, fiscal year {year}: published financial figures and Chief and Council remuneration where extracted, with original ISC PDFs and source notes.'
    body = f'<h1>{esc(name)} financial records · {esc(year)}</h1><p>{esc(name)} is a First Nation in {PROVINCES.get(band.get("province"), "Canada")}. This page organizes its published fiscal-year records from Indigenous Services Canada.</p>'
    body += f'<p><a class="record-button" href="/first-nations/{slug}/?tab={"capital" if "financial" in record else "remuneration"}&amp;year={year}">Explore interactive Nation profile</a></p>'
    if 'financial' in record:
        body += financial_markup(record['financial'], year)
    else:
        body += '<section><h2>Audited financial statements</h2><p>Financial figures for this year have not been published as a parsed summary on OpenBand. This does not establish whether a statement was filed.</p></section>'
    if 'remuneration' in record:
        body += remuneration_markup(record['remuneration'], year)
    else:
        body += '<section><h2>Chief and Council remuneration</h2><p>No publishable parsed remuneration schedule is available on OpenBand for this year. Check the original ISC filing profile for posted documents.</p></section>'
    body += '<section><h2>Other fiscal years</h2><ul class="record-years">' + ''.join(f'<li><a href="{record_path(band, item, slugify)}">{item}</a></li>' for item in years if item != year) + '</ul></section>'
    isc_profile = f"https://services.sac-isc.gc.ca/fnp/main/Search/FederalFundingMain.aspx?BAND_NUMBER={band.get('iscBandNumber', band['id'])}&lang=eng"
    body += f'<section><h2>Sources and interpretation</h2><p>{source_link(isc_profile, "ISC filing profile")}. Figures are extracted from public documents and can contain errors. A missing value means it was not available in this extraction. Compare like fiscal years, read the notes, and confirm amounts in the original PDF.</p><p><a href="/methodology/">How OpenBand handles extraction and corrections</a></p></section>'

    sources = [value.get('sourceUrl') or value.get('href') for value in record.values()]
    dataset = {'@type': 'Dataset', '@id': ORIGIN + path + '#dataset', 'name': f'{name} public financial records {year}',
               'description': description, 'url': ORIGIN + path, 'temporalCoverage': year.replace('-', '/'),
               'spatialCoverage': {'@type': 'Place', 'name': f'{name}, {PROVINCES.get(band.get("province"), "Canada")}, Canada'},
               'creator': {'@type': 'Organization', 'name': 'OpenBand', 'url': ORIGIN + '/about/'}, 'publisher': {'@id': ORIGIN + '/#publisher'},
               'isBasedOn': sources, 'measurementTechnique': 'Automated extraction from publicly posted source PDFs, with review status preserved.'}
    crumbs = [('Home', '/'), ('First Nations', '/first-nations/'), (name, f'/first-nations/{slug}/'), (year, path)]
    return shell(title, description, path, body, schema=[dataset], breadcrumbs=crumbs)

def profile_archive(band, years, slugify):
    if not years:
        return f'<section class="seo-profile-links" data-record-band="{esc(band["id"])}"><h2>Financial records and sources</h2><p>Parsed fiscal-year summaries are not yet available. Review the Nation’s original filing documents above.</p><a href="/methodology/">Sources and methodology</a></section>'
    return (f'<section class="seo-profile-links" data-record-band="{esc(band["id"])}"><h2>Financial records by fiscal year</h2>'
            '<p>Read published financial statement summaries and remuneration schedules with direct source links.</p><ul class="record-years">'
            + ''.join(f'<li><a href="{record_path(band, year, slugify)}">{esc(band["name"])} · {year}</a></li>' for year in years)
            + '</ul><p><a href="/methodology/">Sources and methodology</a> · <a href="/first-nations/">First Nations directory</a></p></section>')

def publish(root: Path, bands, capital, slugify):
    """Return indexed paths; preserve lastmod by hashing actual page content."""
    prior_path = root / 'seo-page-manifest.json'
    prior = json.loads(prior_path.read_text()) if prior_path.exists() else {}
    pages, all_years = {}, {}
    for band in bands:
        years = financial_years(band, capital)
        all_years[str(band['id'])] = years
        for year, record in years.items():
            path = record_path(band, year, slugify)
            pages[path] = annual_page(band, year, record, years, slugify)
    grouped = ''
    for code, province in PROVINCES.items():
        rows = [b for b in bands if b.get('province') == code]
        grouped += f'<section><h2>{province} First Nations</h2><p><a href="/{province.lower()}/">Explore {province} financial records</a></p><ul class="record-directory">' + ''.join(f'<li><a href="/first-nations/{slugify(b["name"])}/">{esc(b["name"])}</a><span>{esc(b.get("treaty") or "Treaty not listed")} · {len(all_years[str(b["id"])])} fiscal years with parsed records</span></li>' for b in rows) + '</ul></section>'
    pages['/first-nations/'] = shell('First Nations Financial Records Directory | OpenBand', 'Browse Saskatchewan and Alberta First Nations: financial statements, Chief and Council remuneration, original source documents, and community profiles.', '/first-nations/', '<h1>First Nations financial records directory</h1><p>Browse the Nations currently covered by OpenBand in Saskatchewan and Alberta. Each profile links to published financial records, source documents, and community information where available.</p>' + grouped, breadcrumbs=[('Home', '/'), ('First Nations', '/first-nations/')])
    pages['/financials/'] = shell('First Nations Financial Statements & Chief and Council Pay | OpenBand', 'Find First Nations audited financial statements, Chief and Council remuneration, and original FNFTA source documents for Saskatchewan and Alberta.', '/financials/', '''<h1>First Nations financial statements and remuneration</h1><p>Find audited financial statements and Chief and Council remuneration schedules for First Nations covered by OpenBand. Start with a Nation, choose a fiscal year, and follow the original Indigenous Services Canada document to check the figures.</p><section><h2>Find a Nation’s financial records</h2><p><a class="record-button" href="/first-nations/">Browse First Nations by name</a></p><ul><li><a href="/saskatchewan/">Saskatchewan First Nations financial records</a></li><li><a href="/alberta/">Alberta First Nations financial records</a></li></ul><p>OpenBand currently covers Saskatchewan and Alberta. Coverage and extraction differ between Nations and fiscal years.</p></section><section><h2>What is an audited financial statement?</h2><p>Financial statements describe the reporting entity’s revenues, expenses, financial position, and other disclosures for a fiscal year. Read the auditor’s report and accompanying notes to understand scope, accounting policies, and qualifications. A consolidated statement can include controlled organizations, so figures may describe more than the band office alone.</p></section><section><h2>What do Chief and Council remuneration schedules show?</h2><p>Remuneration schedules report payments and expenses for the named officials during the stated year. Remuneration, other payments, and travel or expense reimbursements are different fields. A historical row is not evidence that an official currently holds office, and a recorded amount is not a finding about the appropriateness of that payment.</p></section><section><h2>How do I compare two fiscal years?</h2><p>Check that the fiscal-year periods, reporting entities, and accounting categories match. Read the notes for restatements and changes in reporting. A surplus is the difference between reported revenues and expenses; it does not establish how much cash is available for unrestricted spending. Missing data should not be treated as zero.</p></section><section><h2>Where do the original documents come from?</h2><p>OpenBand links to the public FNFTA filings indexed by Indigenous Services Canada. OpenBand is an independent tool and is not the Nation’s official website.</p><p><a href="https://www.sac-isc.gc.ca/eng/1322056355024/1565374106591">ISC: First Nations Financial Transparency Act</a> · <a href="/methodology/">OpenBand methodology and corrections</a></p></section>''', breadcrumbs=[('Home', '/'), ('Financial records', '/financials/')])
    pages['/methodology/'] = shell('Financial Data Sources, Methodology & Corrections | OpenBand', 'How OpenBand extracts First Nations financial records, preserves source references, labels review status, and handles missing values and corrections.', '/methodology/', '''<h1>Sources, methodology, and corrections</h1><p>OpenBand organizes existing public First Nations financial records. Original documents remain the authority for the reported figures.</p><section><h2>Source and coverage</h2><p>Our filing index comes from Indigenous Services Canada’s public FNFTA pages. Financial statement and remuneration links lead back to the original published documents. Current geographic coverage is Saskatchewan and Alberta; not every Nation or fiscal year has a publishable extraction.</p></section><section><h2>Extraction and review</h2><p>Parsers read tables from source PDFs and preserve the fiscal year, document URL, available source references, and review status. Records marked for manual review are excluded from the standalone fiscal-year pages. Financial summaries must be parsed and publishable. Review labels describe extraction status, not an audit opinion from OpenBand.</p></section><section><h2>Missing values and totals</h2><p>Unreported fields remain missing. Zero is shown only when the extracted source field records zero. Standalone remuneration pages keep remuneration and other payments separate. Travel / expenses uses the stored combined field when available, otherwise the sum of disclosed travel, expense, and credit-card components. The combined field is never added to its components. Check the original schedule for the precise meaning of its columns and whether it is audited or unaudited.</p></section><section><h2>Using the records</h2><p>Compare the same fiscal periods and reporting scope. Consolidation, restricted revenues, settlements, accounting adjustments, and restatements can change the interpretation of a headline figure. A public payment or financial result alone does not establish wrongdoing, misuse, or overspending.</p></section><section><h2>Report a correction</h2><p>Open an issue in the public OpenBand repository with the Nation, fiscal year, original document URL, PDF page, and the field you believe is incorrect. Avoid posting private information. Source-backed corrections can be reviewed and incorporated into future builds.</p><p><a href="https://github.com/SevenGen-Studios/OpenBand/issues/new">Submit a source-backed correction</a> · <a href="https://www.sac-isc.gc.ca/eng/1322056355024/1565374106591">Read ISC’s FNFTA information</a></p></section>''', breadcrumbs=[('Home', '/'), ('Methodology', '/methodology/')])
    pages['/about/'] = shell('About OpenBand | First Nations Public Financial Records', 'OpenBand is an independent SevenGenStudios tool for reviewing First Nations public financial records and original source documents.', '/about/', '''<h1>About OpenBand</h1><p>OpenBand is an independent public-records tool by SevenGenStudios. It helps people find and review First Nations financial statements, remuneration schedules, and original public documents.</p><section><h2>Our purpose</h2><p>Make published records easier to locate, read, and verify. Nation profiles also organize community information and public updates where sourced. OpenBand is not a government service or a Nation’s official website.</p></section><section><h2>What is covered?</h2><p>The current directory covers Saskatchewan and Alberta. Financial data comes from published ISC FNFTA filings, with extraction and review status preserved. Coverage can be incomplete, and an absent extraction is not a claim that a Nation did not file a document.</p></section><section><h2>Explore and verify</h2><ul><li><a href="/first-nations/">Browse the Nation directory</a></li><li><a href="/financials/">Find financial statements and remuneration</a></li><li><a href="/methodology/">Read our sources and correction process</a></li><li><a href="https://github.com/SevenGen-Studios/OpenBand">Review the public source repository</a></li></ul></section>''', breadcrumbs=[('Home', '/'), ('About', '/about/')])
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).date().isoformat()
    manifest = {}
    for path, content in pages.items():
        digest = hashlib.sha256(content.encode()).hexdigest()
        old = prior.get(path, {})
        manifest[path] = {'sha256': digest, 'lastmod': old.get('lastmod', today) if old.get('sha256') == digest else today}
        output = root / path.strip('/') / 'index.html'
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content, encoding='utf-8')
    # Remove only annual pages this generator previously owned that became
    # unpublishable. Leave unrelated profiles, maps, and legacy routes intact.
    for path in prior.keys() - manifest.keys():
        if '/financials/' in path and path.startswith('/first-nations/'):
            output = root / path.strip('/') / 'index.html'
            if output.exists():
                output.unlink()
    prior_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
    return manifest, all_years
