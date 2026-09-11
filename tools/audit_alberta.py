"""Reproducible Alberta coverage and source-integrity audit (no network needed)."""
import argparse
import hashlib
import html
import json
import math
import re
from collections import Counter, defaultdict
from urllib.parse import parse_qs, urlsplit
from tools.ingest_alberta import ROOT, CACHE, read, write, now, canonical_url, normalized_name

def audit():
    registry, data = read(ROOT/'alberta-nations.json'), read(ROOT/'data.json')
    capital, enterprise = read(ROOT/'capital-data.json'), read(ROOT/'community-enterprise.json')
    expected = {str(b['id']) for b in registry['nations']}
    bands = [b for b in data['bands'] if b.get('province') == 'AB']
    actual = {str(b['id']) for b in bands}
    issues, rows, documents = [], [], []
    for key, count in Counter(str(b['id']) for b in data['bands']).items():
        if count > 1:
            issues.append({'severity':'error','type':'duplicate_nation_id','id':key})
    for key, count in Counter(normalized_name(b['name']) for b in bands).items():
        if count > 1:
            issues.append({'severity':'error','type':'duplicate_nation_name','name':key})
    urls, hashes = defaultdict(list), defaultdict(list)
    isc_ids, aliases = defaultdict(set), defaultdict(set)
    for band in bands:
        isc_ids[band['iscBandNumber']].add(str(band['id']))
        for name in [band['name'], band.get('officialName','')] + band.get('aliases',[]):
            if name: aliases[normalized_name(name)].add(str(band['id']))
    for bid, ids in isc_ids.items():
        if len(ids)>1 and not (bid==462 and ids=={'462','ab-whitefish-lake-128'}):
            issues.append({'severity':'error','type':'duplicate_isc_identity','iscBandNumber':bid,'nationIds':sorted(ids)})
    for name, ids in aliases.items():
        if len(ids)>1:
            issues.append({'severity':'review','type':'overlapping_nation_alias','name':name,'nationIds':sorted(ids)})
    for band in bands:
        years, remuneration, audited = set(), set(), set()
        seen_years = set()
        for filing in band.get('filings', []):
            if not filing.get('posted') or not filing.get('href'):
                continue
            url = filing['href']
            doc = {'nationId':band['id'],'iscBandNumber':band['iscBandNumber'],'nation':band['name'],
                   'year':filing['year'],'documentType':filing['docType'],'url':url,
                   'title':filing.get('documentTitle',filing['docType']), 'sourceOrganization':filing.get('sourceOrganization'),
                   'retrievedAt':filing.get('retrievedAt'), 'status':filing.get('parse_status'),
                   'warnings':filing.get('warnings',[]),'sha256':filing.get('sha256'),
                   'verificationStatus':filing.get('verificationStatus')}
            doc['pdfRetrieved'] = bool(filing.get('sha256') and filing.get('httpStatus') == 200)
            cache = CACHE / hashlib.sha256(canonical_url(url).encode()).hexdigest()
            if cache.exists():
                payload = cache.read_bytes()
                if payload.lstrip().startswith(b'%PDF-'):
                    doc['sha256'] = hashlib.sha256(payload).hexdigest()
                    doc['pdfRetrieved'] = True
            years.add(doc['year'])
            if 'remuneration' in doc['documentType'].lower(): remuneration.add(doc['year'])
            if 'audited' in doc['documentType'].lower(): audited.add(doc['year'])
            key = (doc['year'],normalized_name(doc['documentType']))
            if key in seen_years:
                issues.append({'severity':'review','type':'multiple_documents_same_type_year','nationId':band['id'],'year':doc['year']})
            seen_years.add(key)
            if not re.fullmatch(r'20\d{2}-20\d{2}',doc['year']) or int(doc['year'][5:]) != int(doc['year'][:4])+1:
                issues.append({'severity':'error','type':'invalid_fiscal_year','document':doc})
            query = parse_qs(urlsplit(url).query)
            if 'BAND_NUMBER_FF' in query and query['BAND_NUMBER_FF'][0] != str(band['iscBandNumber']):
                issues.append({'severity':'error','type':'wrong_nation_document','document':doc})
            if query.get('FY',[doc['year']])[0] != doc['year']:
                issues.append({'severity':'error','type':'wrong_url_fiscal_year','document':doc})
            doc['successfullyParsed'] = filing.get('verificationStatus') == 'automated_validated'
            if doc['successfullyParsed'] and not filing.get('documentChecks',{}).get('identityAndYearConfirmed'):
                issues.append({'severity':'error','type':'unconfirmed_published_identity','document':doc})
            urls[canonical_url(url)].append(doc)
            if doc.get('sha256'): hashes[doc['sha256']].append(doc)
            documents.append(doc)
        summaries = capital.get('bands',{}).get(str(band['id']),{}).get('years',{})
        for year, summary in summaries.items():
            for field in ('totalRevenue','totalExpenses','totalAssets','totalLiabilities','annualSurplusDeficit'):
                value = summary.get(field)
                if value is not None and (not isinstance(value,(int,float)) or not math.isfinite(value) or abs(value)>1e12):
                    issues.append({'severity':'review','type':'suspicious_financial_value','nationId':band['id'],'year':year,'field':field})
            a,l,s = (summary.get(k) for k in ('totalAssets','totalLiabilities','accumulatedSurplus'))
            if all(isinstance(v,(int,float)) for v in (a,l,s)) and abs(a-l-s)>max(10,abs(a)*.01):
                issues.append({'severity':'review','type':'balance_sheet_discrepancy','nationId':band['id'],'year':year})
            if summary.get('statementSections',{}).get('financialPosition') is False:
                issues.append({'severity':'review','type':'missing_financial_position','nationId':band['id'],'year':year})
        businesses = [b['name'] for b in enterprise['businesses'] if str(band['id']) in {str(i) for i in b.get('owningNationIds',[])}]
        source_errors = band.get('sourceErrors',[]) + band.get('officialSiteResearch',{}).get('errors',[])
        issues.extend({'severity':'review','type':'source_unavailable','nationId':band['id'],**e} for e in source_errors)
        if not band.get('logo_verified'):
            issues.append({'severity':'review','type':'logo_unverified','nationId':band['id']})
        rows.append({'id':band['id'],'iscBandNumber':band['iscBandNumber'],'name':band['name'],'treaty':band.get('treaty'),
                     'sharedIscIdentity':band.get('sharedIscIdentity',False),'financialYears':sorted(audited),'remunerationYears':sorted(remuneration),
                     'fiscalYears':sorted(years),'documentCount':sum(1 for d in documents if d['nationId']==band['id']),
                     'verifiedLogo':bool(band.get('logo_verified')),'website':band.get('website'),'verifiedBusinesses':businesses,
                     'sourceErrors':source_errors,'missingYears':[f'{y}-{y+1}' for y in range(2014,2026) if f'{y}-{y+1}' not in years],
                     'disclosureStatus':'individual_disclosures_indexed' if years else 'shared_or_not_found',
                     'relatedDisclosureSources':band.get('relatedDisclosureSources',[])})
    for key, docs in urls.items():
        if len(docs)>1: issues.append({'severity':'error','type':'duplicate_document_url','url':key,'documents':docs})
    for key, docs in hashes.items():
        if len(docs)>1: issues.append({'severity':'review','type':'duplicate_pdf_hash','sha256':key,'documents':[{'nationId':d['nationId'],'year':d['year'],'type':d['documentType']} for d in docs]})
    summary = {'expectedNations':registry['expectedNationCount'],'addedNations':len(bands),'distinctIscBandNumbers':len({b['iscBandNumber'] for b in bands}),
               'countReconciles':actual==expected and len(bands)==registry['expectedNationCount'],
               'financialDocuments':len(documents),'auditedStatements':sum('audited' in d['documentType'].lower() for d in documents),
               'remunerationDocuments':sum('remuneration' in d['documentType'].lower() for d in documents),
               'successfullyParsedDocuments':sum(d['successfullyParsed'] for d in documents),
               'documentsRequiringReview':sum(not d['successfullyParsed'] for d in documents),
               'retrievedPdfs':sum(d.get('pdfRetrieved',False) for d in documents),
               'technicalFailures':sum(d['status']=='error' for d in documents),
               'nationsWithStatements':sum(bool(r['financialYears']) for r in rows),
               'nationsWithRemuneration':sum(bool(r['remunerationYears']) for r in rows),
               'verifiedLogos':sum(r['verifiedLogo'] for r in rows),'officialWebsites':sum(bool(r['website']) for r in rows),
               'verifiedBusinesses':len(read(ROOT/'alberta-businesses.json')['businesses']),
               'nationsWithBusinesses':sum(bool(r['verifiedBusinesses']) for r in rows)}
    result={'generated':now(),'summary':summary,'countSource':registry['countSource'],'identityReconciliation':registry['reconciliation'],
            'missingNations':sorted(expected-actual),'unexpectedNations':sorted(actual-expected),
            'nations':rows,'documents':documents,'issues':issues,
            'limitations':['Roster coverage is complete; financial, leadership, business, map and logo coverage is incomplete.',
                           'Unposted years are not fabricated. An unavailable source is not evidence that no document exists.',
                           'Shared Stoney administration and shared Saddle Lake/Whitefish identities are not duplicated in provincial financial totals.',
                           'Automated validation is not a manual audit opinion. Review original sources before relying on extracted values.']}
    write(ROOT/'alberta-coverage-report.json',result)
    lines=['# Alberta coverage audit','',f"Generated {result['generated']}",''] + [f'- {k}: {v}' for k,v in summary.items()]
    lines += ['',*result['limitations'],'','| Nation | ISC band | Treaty | Audited years | Remuneration years | Logo | Businesses |','|---|---|---|---|---|---|---|']
    for r in rows:
        lines.append('| '+' | '.join([r['name'],str(r['iscBandNumber']),str(r['treaty']),', '.join(r['financialYears']) or 'Not found',', '.join(r['remunerationYears']) or 'Not found','Verified' if r['verifiedLogo'] else 'Unverified','; '.join(r['verifiedBusinesses']) or 'Not verified'])+' |')
    (ROOT/'alberta-coverage-report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    headers=['Nation','ISC band','Treaty','Audited years','Remuneration years','Logo','Website','Verified businesses']
    table=''.join('<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in [r['name'],r['iscBandNumber'],r['treaty'],', '.join(r['financialYears']) or 'Not found',', '.join(r['remunerationYears']) or 'Not found','Verified' if r['verifiedLogo'] else 'Unverified',r['website'] or 'Not verified',', '.join(r['verifiedBusinesses']) or 'Not verified'])+'</tr>' for r in rows)
    page='<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Alberta coverage audit | OpenBand</title><style>body{font:15px system-ui;margin:2rem;color:#21352a}table{border-collapse:collapse;min-width:1000px}td,th{padding:.7rem;border:1px solid #ddd;text-align:left;vertical-align:top}h1{max-width:800px}li{margin:.5rem}</style></head><body><a href="/browse/?province=AB">Back to Alberta</a><h1>Alberta coverage audit</h1><p>48 governments; 47 distinct ISC band numbers. Whitefish Lake #128 and Saddle Lake share ISC 462; Stoney 471 is an umbrella administration.</p><ul>'+''.join('<li>'+html.escape(x)+'</li>' for x in result['limitations'])+'</ul><p>'+html.escape(f"{summary['addedNations']} of {summary['expectedNations']} Nations indexed. {summary['financialDocuments']} disclosures found: {summary['auditedStatements']} audited statements and {summary['remunerationDocuments']} remuneration reports. {summary['successfullyParsedDocuments']} documents passed automated validation; {summary['documentsRequiringReview']} require review. {summary['verifiedLogos']} visually verified logos and {summary['verifiedBusinesses']} verified businesses.")+'</p><p><a href="/alberta-coverage-report.json">Full source, document and review data (JSON)</a> · <a href="/alberta-coverage-report.md">Coverage table (Markdown)</a></p><div style="overflow:auto"><table><thead><tr>'+''.join('<th>'+h+'</th>' for h in headers)+'</tr></thead><tbody>'+table+'</tbody></table></div></body></html>'
    (ROOT/'alberta-coverage-report.html').write_text('<!doctype html>'+page,encoding='utf-8')
    print(json.dumps(summary,indent=2))
    return result

if __name__=='__main__':
    result=audit()
    if not result['summary']['countReconciles'] or any(i['severity']=='error' for i in result['issues']):
        raise SystemExit(1)
