"""Retry review filings across the complete roster without relaxing validation.

Trials are checkpointed separately. --merge accepts only source-bound, validated
results and preserves every previously usable financial summary.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Capital records are large: stream to a sibling file instead of allocating
    # another expanded JSON copy while several OCR workers are active.
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, prefix='.recovery-', suffix='.json',
                                     delete=False, encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=None if path.name == 'capital-data.json' else 2,
                  separators=(',', ':') if path.name == 'capital-data.json' else None, allow_nan=False)
        stream.write('\n')
        temporary = Path(stream.name)
    for attempt in range(6):
        try:
            temporary.replace(path)
            return
        except OSError:
            if attempt == 5:
                raise
            time.sleep(.25)


def usable(summary):
    return bool(summary and (summary.get('publishable') is True or
                (summary.get('parseStatus') == 'parsed' and summary.get('publishable') is not False) or
                summary.get('verified') or summary.get('manualVerified') or
                summary.get('manual_override') or str(summary.get('parser', '')).startswith('manual')))


def candidates(data, capital):
    result = []
    for band in data['bands']:
        for filing in band.get('filings', []):
            summary = capital.get('bands', {}).get(str(band['id']), {}).get('years', {}).get(filing.get('year'), {})
            is_statement = 'audited' in filing.get('docType', '').lower()
            needs_review = filing.get('manual_review_required') or filing.get('parse_status') in {
                'manual_review', 'pending_manual_review', 'pending_openai_opt_in'}
            needs_review |= bool(is_statement and summary.get('parseStatus') == 'manual_review' and not usable(summary))
            if needs_review and filing.get('posted') and filing.get('href'):
                expected = filing.get('sha256') or (summary.get('sha256') if is_statement and summary.get('sourceUrl') == filing['href'] else None)
                result.append({'band': {k: deepcopy(band[k]) for k in ('id', 'name', 'officialName', 'aliases', 'province') if k in band},
                               'filing': deepcopy(filing), 'expectedSha256': expected})
    return sorted(result, key=lambda task: (-int(task['filing']['year'][-4:]), task['band']['name'], task['filing']['docType']))


def validate_result(task, result):
    from tools.capital_parser import validate_summary
    from tools.parser_quality import validate_people
    from tools.reparse_suspicious import filing_problems
    bid, url, update, summary = result
    filing = task['filing']
    reasons = []
    if str(bid) != str(task['band']['id']) or url != filing['href']:
        reasons.append('Source/profile identity changed')
    if not update.get('sha256') or update.get('httpStatus') != 200 or not update.get('documentChecks', {}).get('identityAndYearConfirmed'):
        reasons.append('Document identity and fiscal year not confirmed')
    expected = task.get('expectedSha256') or filing.get('sha256')
    if expected and update.get('sha256') != expected:
        reasons.append('Source digest differs from the stored filing; separate revision review required')
    if update.get('docType', filing['docType']) != filing['docType']:
        reasons.append('Document type differs from the stored listing')
    if update.get('verificationStatus') != 'automated_validated' or update.get('manual_review_required'):
        reasons.extend(update.get('warnings', []))
        reasons.append('Extraction remains unvalidated')
    if 'remuneration' in filing['docType'].lower():
        review = update.get('manualSourceReview') or {}
        complete_review = (review.get('completeSchedule') and review.get('identityAndYearConfirmed')
                           and review.get('sha256') == update.get('sha256')
                           and review.get('sourceRowCount') == len(update.get('people', [])))
        if update.get('sourceTotal') is None and not complete_review:
            reasons.append('Complete printed schedule footer or hash-bound visual review is required')
        checked = validate_people(update.get('people', []), source_total=update.get('sourceTotal'), strict=True)
        if checked['manual_review_required']:
            reasons.extend(checked['warnings'])
        reasons.extend(filing_problems(checked['people']))
    else:
        if not summary or not validate_summary(summary).get('publishable'):
            reasons.append('Financial totals, categories or annual result do not reconcile')
        elif summary.get('fiscalYear') != filing['year'] or summary.get('sha256') != update.get('sha256') or summary.get('sourceUrl') != url:
            reasons.append('Summary source, digest or fiscal year differs from the filing')
        else:
            references = summary.get('sourceReferences', {})
            required_pages = {references.get(field, {}).get('pdfPage')
                              for field in ('totalRevenue', 'totalExpenses', 'annualSurplusDeficit')}
            confirmed_pages = {item['pdfPage'] for item in update.get('documentChecks', {}).get('reportedOperationsPages', [])
                               if item.get('identityConfirmed')}
            if None in required_pages or not required_pages.issubset(confirmed_pages):
                reasons.append('Nation identity is not confirmed on every page used for reported statement totals')
    return list(dict.fromkeys(reasons))


def windows_coordinate_ocr(payload, page_numbers=None, stop_when=None, extra_pages=0):
    """Render directly into memory, keeping OCR words tied to their page columns."""
    import pypdfium2
    import winocr
    from tools.local_ocr import coordinate_lines
    pages, aligned, processed, warnings = [], [], [], []
    with closing(pypdfium2.PdfDocument(payload)) as pdf:
        selected = sorted(set(page_numbers or range(1, min(len(pdf), 16) + 1)))
        if len(selected) >= 10 and selected == list(range(1, len(selected) + 1)):
            selected = list(range(1, min(len(pdf), 16) + 1))
        pages = [''] * max(selected, default=0)
        stop_after = None
        for index, number in enumerate(selected):
            with closing(pdf[number - 1]) as page:
                scale = min(2.5, 2200 / max(page.get_size()))
                with closing(page.render(scale=scale)) as bitmap:
                    recognized = winocr.recognize_pil_sync(bitmap.to_pil())
            items = []
            for line in recognized.get('lines', []):
                for word in line.get('words', []):
                    box = word['bounding_rect']
                    x, y = box['x'], box['y']
                    right, bottom = x + box['width'], y + box['height']
                    items.append(([[x, y], [right, y], [right, bottom], [x, bottom]], word['text']))
            rendered = coordinate_lines(items, align_financial_columns=True, return_metadata=True)
            processed.append(number)
            if re.search(r'\b\d{1,3}\.\d{3}\b', rendered['text']):
                warnings.append(f'Page {number}: ambiguous OCR thousands separator; page withheld')
                continue
            pages[number - 1] = rendered['text']
            if rendered['financialColumnsAligned']:
                aligned.append(number)
            if stop_after is None and stop_when and stop_when(pages):
                stop_after = index + extra_pages
            if stop_after is not None and index >= stop_after:
                break
    return {'status': 'ok_ocr_text' if any(pages) else 'error_ocr_empty', 'pages': pages,
            'page_count': len(processed), 'page_numbers': processed, 'warnings': warnings,
            'financialColumnPages': aligned, 'engine': 'windows_coordinate'}


def configure(task, args):
    from tools import ingest_alberta as engine, local_ocr
    shared = Path(args.cache_source).resolve() if args.cache_source else ROOT
    engine.PROVINCE = task['band'].get('province', '')
    engine.SOURCE_CACHE = ROOT / 'tools' / ('manitoba-source-cache' if engine.PROVINCE == 'MB' else 'alberta-source-cache')
    engine.CACHE = shared / '.openband-ocr/alberta'
    engine.NON_PDF_ADAPTER = None
    original_download = engine.download
    manifest = shared / 'research/bandy-financial/all-nations-2026-10-09/manifest.json'
    source_index = {}
    if manifest.exists():
        for document in read(manifest).get('documents', []):
            source_index[engine.canonical_url(document['sourceUrl'])] = shared / 'research/bandy-financial/all-nations-2026-10-09/pdf-cache' / (document['documentKey'] + '.pdf')

    def download(url, refresh=False):
        key = hashlib.sha256(engine.canonical_url(url).encode()).hexdigest()
        paths = [shared / '.openband-ocr/alberta' / key, shared / '.openband-ocr/saskatchewan' / key,
                 source_index.get(engine.canonical_url(url))]
        for path in paths:
            if path and path.is_file():
                payload = path.read_bytes()
                if payload.lstrip().startswith(b'%PDF-'):
                    return payload
        return original_download(url, refresh)
    engine.download = download
    if engine.PROVINCE == 'MB':
        from tools import manitoba_source_formats
        engine.NON_PDF_ADAPTER = manitoba_source_formats.parse_non_pdf

    real_ocr = local_ocr.ocr_pdf_bytes
    def cached_ocr(payload, page_numbers=None, **kwargs):
        digest = hashlib.sha256(payload).hexdigest()
        selections = [sorted(page_numbers or [])]
        if page_numbers:
            selections.append(list(range(1, max(page_numbers) + 1)))
        variants = ('windows', 'rapidocr:financial-columns-v3', 'rapidocr:financial-columns-v2', 'rapidocr', '')
        requested = os.getenv('OPENBAND_OCR_ENGINE', 'windows')
        if args.mode == 'ocr':
            variants = tuple(v for v in variants if v.startswith(requested))
        for selected in selections:
            for dpi in ('180', '220', '240', '300'):
                for variant in variants:
                    key = hashlib.sha256((digest + repr(selected) + dpi + variant).encode()).hexdigest()
                    path = engine.CACHE / (key + '.ocr.json')
                    if path.exists():
                        return read(path)
        if args.mode == 'ocr':
            if requested == 'windows-coordinate':
                return windows_coordinate_ocr(payload, page_numbers=page_numbers, **kwargs)
            return real_ocr(payload, page_numbers=page_numbers, **kwargs)
        return {'pages': [], 'status': 'deferred', 'warnings': ['No matching cached OCR; fresh OCR is a separate trial']}
    if args.mode == 'native':
        local_ocr.ocr_pdf_bytes = lambda *a, **kw: {'pages': [], 'status': 'deferred', 'warnings': ['Native-text trial; OCR deferred']}
    else:
        local_ocr.ocr_pdf_bytes = cached_ocr
    return engine


def worker(args):
    scratch = ROOT / '.openband-ocr' / 'tmp'
    scratch.mkdir(parents=True, exist_ok=True)
    tempfile.tempdir = str(scratch)
    task = read(args.worker)
    engine = configure(task, args)
    started = time.monotonic()
    result = engine.parse_one((task['band'], task['filing'], args.mode != 'native'))
    reasons = validate_result(task, result)
    write(args.result, {'result': result, 'accepted': not reasons, 'reasons': reasons,
                        'seconds': round(time.monotonic() - started, 2), 'mode': args.mode})


def merge_result(data, capital, task, result):
    from tools.capital_parser import save_summary
    bid, url, update, summary = result
    band = next(b for b in data['bands'] if str(b['id']) == str(bid))
    filing = next(f for f in band['filings'] if f.get('href') == url)
    candidate = {**filing, **deepcopy(update)}
    if summary:
        year = task['filing']['year']
        existing = capital.get('bands', {}).get(str(bid), {}).get('years', {}).get(year)
        if not usable(existing):
            trial = {'bands': {str(bid): {'name': band['name'], 'years': {year: deepcopy(existing or {})}}}}
            save_summary(trial, band, candidate, deepcopy(summary))
            reviewed = trial['bands'][str(bid)]['years'][year]
            if not reviewed.get('publishable') or candidate.get('manual_review_required'):
                return 'Existing field review prevents publication of the new summary'
            capital.setdefault('bands', {}).setdefault(str(bid), {'name': band['name']}).setdefault('years', {})[year] = reviewed
    filing.clear()
    filing.update(candidate)
    return None


def run(args):
    data, capital = read(ROOT / 'data.json'), read(ROOT / 'capital-data.json')
    tasks = candidates(data, capital)
    prior = {}
    if args.recheck_from:
        for path in (Path(args.recheck_from) / 'checkpoints').glob('*.json'):
            if path.name.endswith('.task.json'):
                continue
            outcome = read(path)
            if not any('context manager' in r for r in outcome.get('reasons', [])):
                if outcome.get('result'):
                    key = (str(outcome['result'][0]), outcome['result'][1])
                else:
                    previous_task = read(path.with_name(path.stem + '.task.json'))
                    key = (str(previous_task['band']['id']), previous_task['filing']['href'])
                if key not in prior or path.stat().st_mtime > prior[key][0]:
                    prior[key] = (path.stat().st_mtime, outcome)
    if args.document_type != 'all':
        tasks = [t for t in tasks if ('remuneration' in t['filing']['docType'].lower()) == (args.document_type == 'pay')]
    if args.band_id:
        tasks = [t for t in tasks if str(t['band']['id']) in args.band_id]
    if args.scanned_only:
        tasks = [t for t in tasks if (str(t['band']['id']), t['filing']['href']) in prior
                 and prior[str(t['band']['id']), t['filing']['href']][1].get('result')
                 and prior[str(t['band']['id']), t['filing']['href']][1]['result'][2].get('sha256')
                 and prior[str(t['band']['id']), t['filing']['href']][1]['result'][2].get('nativeTextCharacters', 1000) < 100]
    if args.recheck_only:
        tasks = [t for t in tasks if (str(t['band']['id']), t['filing']['href']) in prior]
    if args.limit:
        tasks = tasks[:args.limit]
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    write(output / 'inventory.json', tasks)
    revision = hashlib.sha256(b''.join((ROOT / name).read_bytes() for name in (
        'tools/recover_review_filings.py', 'tools/ingest_alberta.py', 'tools/capital_parser.py',
        'tools/parser_quality.py', 'run_scraper.py', 'tools/local_ocr.py',
        'manual_overrides/audit-remuneration-reviews.json',
        'tools/manitoba-source-cache/remuneration-reviews.json'))).hexdigest()[:16]
    def attempt(task):
        key_material = [task['band'], task['filing']['href'], task['filing']['docType'], task['filing']['year'],
                        task['expectedSha256'], revision, args.mode, os.getenv('OPENBAND_OCR_ENGINE'), os.getenv('OPENBAND_OCR_DPI')]
        key = hashlib.sha256(json.dumps(key_material, sort_keys=True).encode()).hexdigest()
        source, destination = output / 'checkpoints' / (key + '.task.json'), output / 'checkpoints' / (key + '.json')
        if destination.exists():
            outcome = read(destination)
            if outcome.get('result'):
                outcome['reasons'] = validate_result(task, outcome['result'])
                outcome['accepted'] = not outcome['reasons']
            return task, outcome
        prior_outcome = prior.get((str(task['band']['id']), task['filing']['href']))
        if args.recheck_only and prior_outcome:
            outcome = deepcopy(prior_outcome[1])
            if outcome.get('result'):
                outcome['reasons'] = validate_result(task, outcome['result'])
                outcome['accepted'] = not outcome['reasons']
            write(source, task)
            write(destination, outcome)
            return task, outcome
        write(source, task)
        command = [sys.executable, str(Path(__file__).resolve()), '--worker', str(source), '--result', str(destination), '--mode', args.mode]
        if args.cache_source:
            command += ['--cache-source', args.cache_source]
        try:
            subprocess.run(command, timeout=args.timeout, capture_output=True, check=True, text=True, encoding='utf-8', errors='replace')
            return task, read(destination)
        except Exception as exc:
            if destination.exists():
                return task, read(destination)
            outcome = {'accepted': False, 'reasons': [type(exc).__name__ + ': ' + str(exc)[-800:]], 'mode': args.mode}
            write(destination, outcome)
            return task, outcome
    report = {'mode': args.mode, 'candidateCount': len(tasks), 'accepted': [], 'unresolved': []}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        pending = [pool.submit(attempt, task) for task in tasks]
        for index, future in enumerate(as_completed(pending), 1):
            task, outcome = future.result()
            entry = {'bandId': str(task['band']['id']), 'band': task['band']['name'], 'province': task['band'].get('province'),
                     'year': task['filing']['year'], 'documentType': task['filing']['docType'], 'sourceUrl': task['filing']['href'],
                     'reasons': outcome['reasons']}
            merged_error = merge_result(data, capital, task, outcome['result']) if outcome['accepted'] and args.merge else None
            if outcome['accepted'] and not merged_error:
                entry['sha256'] = outcome['result'][2]['sha256']
                report['accepted'].append(entry)
                print(f"[{index}/{len(tasks)}] RECOVERED {entry['band']} {entry['year']} {entry['documentType']}", flush=True)
            else:
                if merged_error:
                    entry['reasons'] = [merged_error]
                report['unresolved'].append(entry)
            if index % 25 == 0 or index == len(tasks):
                write(output / 'report.json', report)
                print(f"Progress {index}/{len(tasks)}; recovered {len(report['accepted'])}; unresolved {len(report['unresolved'])}", flush=True)
    if args.merge and report['accepted']:
        from datetime import datetime, timezone
        data['generated'] = capital['generated'] = datetime.now(timezone.utc).isoformat()
        write(ROOT / 'data.json', data)
        write(ROOT / 'capital-data.json', capital)
    write(output / 'report.json', report)
    print(f"Completed {args.mode}: {len(report['accepted'])} recoveries from {len(tasks)} trials", flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['native', 'cached', 'ocr'], default='native')
    parser.add_argument('--cache-source')
    parser.add_argument('--output', default='.openband-ocr/review-recovery')
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--timeout', type=int, default=90)
    parser.add_argument('--limit', type=int)
    parser.add_argument('--merge', action='store_true')
    parser.add_argument('--recheck-from', help='Use earlier trials as the source inventory for rechecks or scanned-only retries')
    parser.add_argument('--recheck-only', action='store_true')
    parser.add_argument('--scanned-only', action='store_true')
    parser.add_argument('--document-type', choices=['all', 'pay', 'capital'], default='all')
    parser.add_argument('--band-id', action='append')
    parser.add_argument('--worker')
    parser.add_argument('--result')
    args = parser.parse_args()
    if args.worker:
        worker(args)
    else:
        run(args)
