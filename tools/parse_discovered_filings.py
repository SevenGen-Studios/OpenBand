"""Verify downloaded discovery checkpoints and import only qualifying results.

The work directory contains selection.json, <band>-<year>-audit/pay.pdf,
the native worker's .native.json result, and optional hash-bound .vision.json
word boxes. PDFs and OCR caches stay private; the report retains proposals,
source URLs, hashes, page evidence, and reasons for withholding publication.
Run recover_review_filings.py --worker first to create native checkpoints.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import capital_parser, ingest_alberta
from tools.bandy_financial import read_pdf, is_statement, project_page
from tools.recover_review_filings import read, write, validate_result, merge_result, usable

CORE_FIELDS = ('totalRevenue', 'totalExpenses', 'annualSurplusDeficit')
IMPORTANT_FIELDS = CORE_FIELDS + ('totalAssets', 'totalLiabilities',
    'netFinancialAssetsDebt', 'accumulatedSurplus', 'cash', 'totalFinancialAssets')


def money(text):
    text = text.strip().replace('$', '').replace(',', '').replace(' ', '')
    if not re.fullmatch(r'\(?-?\d+(?:\.\d+)?\)?', text):
        return None
    return -float(text[1:-1]) if text.startswith('(') and text.endswith(')') else float(text)


def optical_evidence(summary, rows, optical):
    """Match independently read amounts to the SAME actual-year cell and page.

    A page-wide occurrence is insufficient: the row baseline and actual-column
    position must agree. Missing signs, comparative figures, and budget cells
    cannot establish agreement. Twenty-two points allow right-aligned amounts
    extending beyond short year headings; adjacent financial columns are wider.
    """
    evidence, issues = {}, []
    for field in IMPORTANT_FIELDS:
        value = summary.get(field)
        reference = summary.get('sourceReferences', {}).get(field)
        if value is None or not reference:
            continue  # Derived totals have no independently reported cell.
        candidates = [row for row in rows if row['value'] == value
                      and row['reference']['pdfPage'] == reference.get('pdfPage')
                      and row['reference'].get('yearValidated')]
        for row in candidates:
            ref = row['reference']
            box = ref['bbox']
            middle = (box[1] + box[3]) / 2
            matches = [word for page in optical['pages'] if page['page'] == ref['pdfPage']
                       for word in page['words']
                       if abs((word['top'] + word['bottom']) / 2 - middle) < 6
                       and abs(word['x1'] - ref['columnRight']) < 22
                       and money(word['text']) == value]
            if matches:
                evidence[field] = {'normalizedValue': value, 'currency': 'CAD', 'units': 'dollars',
                    'fiscalYear': summary['fiscalYear'], 'pdfPage': ref['pdfPage'],
                    'statement': reference.get('table'), 'native': ref, 'independentOcr': matches[0],
                    'method': 'native PDF geometry + Apple Vision OCR',
                    'verificationStatus': 'independently_checked'}
                break
        if field not in evidence:
            issues.append(f'{field}: independent actual-column check unavailable or disagrees')
    for field in CORE_FIELDS:
        if field not in evidence and not any(issue.startswith(field + ':') for issue in issues):
            issues.append(f'{field}: reported total has no independent source-cell evidence')
    return evidence, issues


def verify_task(task, work):
    band, filing = task['band'], task['filing']
    kind = 'pay' if 'remuneration' in filing['docType'].lower() else 'audit'
    key = f"{band['id']}-{filing['year']}-{kind}"
    payload = (work / (key + '.pdf')).read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    expected = task.get('expectedSha256') or filing.get('sha256')
    if expected and expected != digest:
        raise ValueError('Downloaded PDF differs from the discovered source digest')
    result = deepcopy(read(work / (key + '.native.json'))['result'])
    update = result[2]
    if str(result[0]) != str(band['id']) or result[1] != filing['href'] or update.get('sha256') != digest:
        raise ValueError('Native checkpoint does not belong to this source PDF')
    pdf = read_pdf(payload, {})
    pages = [page['text'] for page in pdf['pages']]
    optical_path = work / (key + '.vision.json')
    optical = read(optical_path) if optical_path.exists() else {}
    identity_issues = ingest_alberta.document_identity(pages, band, filing)
    if identity_issues and optical.get('sha256') == digest:
        recognized = [''] * max((p['page'] for p in optical.get('pages', [])), default=0)
        for page in optical.get('pages', []):
            recognized[page['page']-1] = page['text']
        identity_issues = ingest_alberta.document_identity(recognized, band, filing)
    update['documentChecks'] = {'identityAndYearConfirmed': not identity_issues,
                               'warnings': identity_issues}
    evidence, issues = {}, list(identity_issues)
    if optical.get('sha256') != digest:
        issues.append('Independent OCR checkpoint missing or source digest differs')
        optical = {'pages': []}
    if kind == 'pay':
        reviewed = ingest_alberta.reviewed_remuneration(band, filing, digest)
        if reviewed:
            update.update(reviewed)
            update['verificationStatus'] = 'automated_validated'
            evidence = {'schedule': deepcopy(update['manualSourceReview'])}
        else:
            issues.append('Complete hash-bound schedule and column classification require source review')
    else:
        from tools.filing_review.extraction import identify
        aliases = list(band.get('aliases') or [])
        if band.get('officialName'):
            aliases.append(band['officialName'])
        update['auditMetadata'] = identify({'name': band['name'], 'aliases': aliases,
            'bandNumber': band.get('iscBandNumber', band['id']), 'fiscalYear': filing['year']},
            pdf['pages'], filing['href'])
        summary = capital_parser.parse_page_texts(pages, filing['href'], filing['year'],
                                                require_reported_totals=True)
        summary['sha256'] = digest
        # The shared native parser remains the first fallback for fragmented
        # PDF text. Every accepted total still needs actual-column OCR evidence.
        if not summary.get('publishable') and result[3] and result[3].get('publishable'):
            summary = result[3]
        rows = []
        for page in pdf['pages']:
            if is_statement(page):
                _, projected, _ = project_page(page, filing['year'], int(filing['year'][-4:]))
                rows.extend(projected)
        evidence, optical_issues = optical_evidence(summary, rows, optical)
        issues.extend(optical_issues)
        # The cover and the table must both identify the Nation. A corporate
        # statement bundled behind a Nation cover cannot pass this check.
        observations = []
        for number in sorted({summary.get('sourceReferences', {}).get(field, {}).get('pdfPage')
                              for field in CORE_FIELDS} - {None}):
            matched = not any(reason.startswith('Nation identity') for reason in
                ingest_alberta.document_identity(['\n'.join(pages[number-1].splitlines()[:10])], band, filing))
            observations.append({'pdfPage': number, 'identityConfirmed': matched})
        update['documentChecks']['reportedOperationsPages'] = observations
        audit_text = '\n'.join(pages[:7])
        if not re.search(r"independent auditor[’'s\s]*report", audit_text, re.I):
            issues.append('Independent auditor report not confirmed in native text')
        result[3] = summary
        update.update(parse_status=summary.get('parseStatus'), warnings=summary.get('warnings', []),
                      manual_review_required=not summary.get('publishable'),
                      verificationStatus='automated_validated' if summary.get('publishable') else 'manual_review')
    update['independentVerification'] = {'sourceSha256': digest, 'figures': evidence,
        'status': 'review_required' if issues else 'source_checks_passed',
        'rules': 'Document identity, current-year source cells, independent extraction, and applicable reconciliation; OCR confidence alone is insufficient.'}
    update['extractionMethod'] = 'Native PDF extraction with independent OCR and source review'
    update['ocrStatus'] = 'independently_checked' if optical['pages'] else 'review_required'
    update['ocrEngine'] = 'apple_vision_pyobjc_13' if optical['pages'] else 'unavailable'
    update['secondaryExtraction'] = {'sha256': digest, 'engine': update['ocrEngine'],
        'pages': [{'pdfPage': p['page'], 'rawText': p['text']} for p in optical['pages']]}
    rapid_path = work / (key + '.rapidocr.json')
    if rapid_path.exists():
        # Additional scanned-page OCR is evidence, never an approval override.
        update['secondaryExtraction']['scannedCrossCheck'] = {'engine': 'rapidocr_onnxruntime_1.4.4',
                                                             'pages': read(rapid_path)}
    issues += validate_result(task, result)
    return result, list(dict.fromkeys(issues))


def run(work, data_path, capital_path, report_path, apply=False):
    data, capital = read(data_path), read(capital_path)
    report = {'generated': datetime.now(timezone.utc).isoformat(), 'records': [],
              'policy': 'Only complete validated extractions are imported. Existing verified financial values are preserved. Comparative columns never create a filing.'}
    for selected in read(work / 'selection.json'):
        band, filing = selected['band'], selected['filing']
        task = {'band': {k: deepcopy(band[k]) for k in ('id', 'name', 'officialName', 'aliases', 'province') if k in band},
                'filing': filing, 'expectedSha256': filing.get('sha256')}
        record = {'bandId': band['id'], 'firstNation': band['name'], 'province': band['province'],
                  'bandNumber': band.get('iscBandNumber', band['id']), 'fiscalYear': filing['year'],
                  'documentType': filing['docType'], 'sourceUrl': filing.get('sourcePage') or filing.get('sourceUrl') or filing['href'],
                  'pdfUrl': filing['href']}
        stored_band = next(b for b in data['bands'] if str(b['id']) == str(band['id']))
        stored = next(f for f in stored_band['filings'] if f.get('href') == filing['href'])
        record['previousFiling'] = deepcopy(stored)
        record['previousSummary'] = deepcopy(capital.get('bands', {}).get(str(band['id']), {}).get('years', {}).get(filing['year']))
        try:
            result, reasons = verify_task(task, work)
            record.update(sha256=result[2]['sha256'], reasons=reasons,
                          evidence=result[2].get('independentVerification'), proposedExtraction=result)
            source_review_path = work / (f"{band['id']}-{filing['year']}-{'pay' if 'remuneration' in filing['docType'].lower() else 'audit'}.source-review.json")
            if source_review_path.exists():
                source_review = read(source_review_path)
                if source_review.get('sha256') == result[2]['sha256']:
                    record['sourceReview'] = source_review
                    reasons.extend(source_review.get('unresolvedDiscrepancies', []))
            if stored.get('people') and not stored.get('manual_review_required') and stored.get('people') != result[2].get('people'):
                reasons.append('Existing published official values differ; replacement requires administrator approval')
            if not reasons:
                failure = merge_result(data, capital, task, result)
                if failure:
                    reasons.append(failure)
            record['status'] = 'Review Required' if reasons else 'Verified'
            if reasons:
                stored_band = next(b for b in data['bands'] if str(b['id']) == str(band['id']))
                stored = next(f for f in stored_band['filings'] if f.get('href') == filing['href'])
                # Preserve prior values, placing proposals exclusively in the
                # report. Availability remains public even when values fail.
                if not stored.get('people') and stored.get('verificationStatus') != 'automated_validated':
                    stored.update(parse_status='manual_review', manual_review_required=True,
                        verificationStatus='manual_review', sha256=result[2]['sha256'],
                        ocrStatus='review_required', warnings=list(dict.fromkeys(stored.get('warnings', []) + reasons)),
                        extractionReviewReport=report_path.name)
        except Exception as error:
            record.update(status='Review Required', reasons=[f'{type(error).__name__}: {error}'])
        report['records'].append(record)
        print(band['name'], filing['year'], record['documentType'], record['status'], flush=True)
    report['counts'] = {'processed': len(report['records']),
        'verified': sum(r['status'] == 'Verified' for r in report['records']),
        'reviewRequired': sum(r['status'] == 'Review Required' for r in report['records'])}
    report.update(report['counts'])
    write(report_path, report)
    if apply:
        write(data_path, data)
        write(capital_path, capital)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--data', type=Path, default=ROOT / 'data.json')
    parser.add_argument('--capital', type=Path, default=ROOT / 'capital-data.json')
    parser.add_argument('--report', type=Path, default=ROOT / 'filing-extraction-report.json')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    result = run(args.work_dir, args.data, args.capital, args.report, args.apply)
    print(json.dumps(result['counts']))
