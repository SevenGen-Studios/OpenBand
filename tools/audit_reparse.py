"""Bounded source-checked recovery of pending filings; never replace working rows.

Uses the shared Alberta parser for either province. Paid extraction stays off.
Results are checkpointed per source document before any shared dataset is saved.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from tools.ingest_alberta import ROOT, bounded_parse, read, write, now, canonical_url
from tools.capital_parser import save_summary


def recoverable(filing, summary=None):
    if not filing.get('posted') or not filing.get('href') or filing.get('people'):
        return False
    if 'audited' in filing.get('docType','').lower():
        # Legacy scrapes used not_required for statements before capital parsing
        # existed. That label is not evidence of a validated financial summary.
        return not (summary and summary.get('publishable') and summary.get('parseStatus')=='parsed')
    return bool(filing.get('manual_review_required') or
                filing.get('parse_status') not in {'parsed', 'not_posted', 'not_applicable_wrong_document'})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--band', action='append', default=[])
    parser.add_argument('--province', choices=['SK','AB'])
    parser.add_argument('--source-list',help='Restrict to newDocuments in an official listing review report')
    parser.add_argument('--workers', type=int, choices=[1,2,3], default=1)
    parser.add_argument('--limit', type=int, default=30)
    parser.add_argument('--ocr', action='store_true')
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--report', default='audit-reparse-results.json')
    args = parser.parse_args()
    data = read(ROOT / 'data.json')
    capital = read(ROOT / 'capital-data.json')
    source_urls = {canonical_url(f['href']) for r in read(args.source_list)['results'] for f in r.get('newDocuments',[])} if args.source_list else None
    targets = [(band, filing) for band in data['bands']
               if (not args.band or str(band['id']) in args.band)
               and (not args.province or band['province'] == args.province)
               for filing in band.get('filings', []) if recoverable(filing,capital.get('bands',{}).get(str(band['id']),{}).get('years',{}).get(filing['year']))
               and (source_urls is None or canonical_url(filing['href']) in source_urls)]
    if args.limit:
        targets = targets[:args.limit]
    outcomes = []
    def parse_target(target):
        band, filing = target
        identity = {key: deepcopy(band[key]) for key in ('id', 'name', 'officialName', 'aliases') if key in band}
        return bounded_parse((identity, deepcopy(filing), args.ocr))
    pool = ThreadPoolExecutor(max_workers=args.workers)
    for index, ((band, filing), result) in enumerate(zip(targets, pool.map(parse_target, targets)), 1):
        bid, url, update, summary = result
        existing = capital.get('bands', {}).get(bid, {}).get('years', {}).get(filing['year'])
        accepted = bool(not update.get('manual_review_required') and
                        update.get('verificationStatus') == 'automated_validated' and
                        (update.get('people') or summary and summary.get('publishable')))
        if update.get('people') and update.get('sourceTotal') is None and not (update.get('manualSourceReview') or {}).get('completeSchedule'):
            accepted = False  # Missing printed column/footer evidence needs visual review.
        if accepted and existing and existing.get('publishable') and summary:
            accepted = False  # This recovery command is for gaps, not replacements.
        outcome = {'bandId': bid, 'name': band['name'], 'province': band['province'],
                   'year': filing['year'], 'document': filing['docType'], 'sourceUrl': url,
                   'before': filing.get('parse_status'), 'status': 'FIXED' if accepted and args.write else 'NEEDS MANUAL REVIEW',
                   'validatedCandidate': accepted,
                   'parserStatus': update.get('parse_status'), 'sha256': update.get('sha256'),
                   'checkedAt': update.get('lastChecked'), 'warnings': update.get('warnings', []),
                   'people': len(update.get('people') or []), 'documentChecks': update.get('documentChecks')}
        outcomes.append(outcome)
        if accepted and args.write:
            data['generated'] = now()
            filing.update(update)
            filing['reparsed'] = now()
            filing.setdefault('retrievedAt', update.get('lastChecked'))
            if summary:
                save_summary(capital, band, filing, summary)
            write(ROOT / 'data.json', data)
            write(ROOT / 'capital-data.json', capital)
        write(ROOT / args.report, {'generated': now(), 'write': args.write, 'outcomes': outcomes})
        print(f"[{index}/{len(targets)}] {band['name']} {filing['year']}: {outcome['status']} ({outcome['people']} rows)", flush=True)
    pool.shutdown()


if __name__ == '__main__':
    main()
