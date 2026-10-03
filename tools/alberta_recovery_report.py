"""Document Alberta recoveries against a supplied pre-recovery Git revision."""
import argparse
import json
import subprocess
from collections import Counter
from urllib.parse import quote
from tools.ingest_alberta import ROOT, read, write, now

def validated(filing):
    return filing.get('verificationStatus') == 'automated_validated' and not filing.get('manual_review_required')

def generate(baseline_revision="ebcf2bb", round_baseline=None):
    baseline = json.loads(subprocess.check_output(['git', 'show', f'{baseline_revision}:data.json']))
    current = read(ROOT / 'data.json')
    old_capital = json.loads(subprocess.check_output(['git', 'show', f'{baseline_revision}:capital-data.json']))
    capital = read(ROOT / 'capital-data.json')
    assert [b for b in baseline['bands'] if b.get('province') != 'AB'] == [
        b for b in current['bands'] if b.get('province') != 'AB']
    ab_ids = {str(b['id']) for b in current['bands'] if b.get('province') == 'AB'}
    assert {k: v for k, v in old_capital['bands'].items() if k not in ab_ids} == {
        k: v for k, v in capital['bands'].items() if k not in ab_ids}
    old = {(str(b['id']), f['href']): f for b in baseline['bands'] if b.get('province') == 'AB'
           for f in b['filings'] if f.get('posted') and f.get('href')}
    rows = []
    for b in current['bands']:
        if b.get('province') != 'AB':
            continue
        for f in b['filings']:
            key = str(b['id']), f.get('href')
            previous = old.get(key)
            if not previous or validated(previous):
                continue
            recovered = validated(f)
            attempted = f.get('parserRevision') != previous.get('parserRevision') or f.get(
                'lastReparseAttempt') != previous.get('lastReparseAttempt') or f.get('lastChecked') != previous.get('lastChecked')
            rows.append({'nationId': b['id'], 'nation': b['name'], 'year': f['year'],
                         'documentType': f['docType'], 'sourcePdf': f['href'], 'attempted': attempted,
                         'recovered': recovered, 'status': f.get('parse_status'),
                         'parserRevision': f.get('parserRevision'), 'ocrStatus': f.get('ocrStatus'), 'ocrEngine': f.get('ocrEngine'),
                         'documentChecks': f.get('documentChecks'), 'listedDocType': f.get('listedDocType'),
                         'manualSourceReview': f.get('manualSourceReview'),
                         'warnings': f.get('reparseWarnings', f.get('warnings', [])) if not recovered else f.get('warnings', [])})
    before_valid = sum(validated(f) for f in old.values())
    added = sum(r['recovered'] for r in rows)
    old_financial = {(bid, year) for bid in ab_ids for year, summary in old_capital.get('bands', {}).get(bid, {}).get('years', {}).items() if summary.get('publishable')}
    new_financial = {(bid, year) for bid in ab_ids for year, summary in capital.get('bands', {}).get(bid, {}).get('years', {}).items() if summary.get('publishable')}
    summary = {'totalDocuments': len(old), 'validatedBefore': before_valid,
               'validatedAfter': before_valid + added, 'reviewBefore': len(rows),
               'recoveredDocuments': added, 'reviewAfter': len(rows) - added,
               'originalReviewDocumentsAttempted': sum(r['attempted'] for r in rows),
               'recoveredByType': dict(Counter(r['documentType'] for r in rows if r['recovered'])),
               'publishableFinancialYearsBefore': len(old_financial), 'publishableFinancialYearsAfter': len(new_financial),
               'newlyPublishableFinancialYears': len(new_financial - old_financial),
               'saskatchewanRecordsUnchanged': True}
    summary['correctedPreviouslyContradictoryValidationFlags'] = sum(
        f.get('verificationStatus') == 'automated_validated' and not validated(f) for f in old.values())
    assert summary['validatedAfter'] == sum(validated(f) for b in current['bands'] if b.get('province') == 'AB'
                                          for f in b['filings'] if f.get('posted') and f.get('href'))
    result = {'generated': now(), 'baselineCommit': subprocess.check_output(['git', 'rev-parse', baseline_revision]).decode().strip(),
              'summary': summary, 'documents': sorted(rows, key=lambda r: (r['nation'], r['year'], r['documentType']))}
    if round_baseline:
        previous_data = json.loads(subprocess.check_output(['git', 'show', f'{round_baseline}:data.json']))
        previous_capital = json.loads(subprocess.check_output(['git', 'show', f'{round_baseline}:capital-data.json']))
        prior = {(str(b['id']), f['href']): f for b in previous_data['bands'] if b.get('province') == 'AB'
                 for f in b['filings'] if f.get('posted') and f.get('href') and not validated(f)}
        current_filings = {(str(b['id']), f.get('href')): f for b in current['bands'] if b.get('province') == 'AB'
                           for f in b['filings']}
        newly_validated = [current_filings[key] for key in prior if validated(current_filings[key])]
        prior_years = {(bid, year) for bid in ab_ids for year, s in
                       previous_capital.get('bands', {}).get(bid, {}).get('years', {}).items() if s.get('publishable')}
        result['latestPass'] = {
            'baselineCommit': subprocess.check_output(['git', 'rev-parse', round_baseline]).decode().strip(),
            'reviewBefore': len(prior), 'recoveredDocuments': len(newly_validated),
            'recoveredByType': dict(Counter(f['docType'] for f in newly_validated)),
            'newlyPublishableFinancialYears': len(new_financial - prior_years),
        }
    write(ROOT / 'alberta-parser-recovery-report.json', result)
    lines = ['# Alberta filing parser recovery', '', f"Generated {result['generated']}", '',
             f"Reprocessed {summary['originalReviewDocumentsAttempted']} of {len(rows)} previously unresolved documents.",
             f"Validated filings increased from {before_valid} to {before_valid + added}; the review queue decreased from {len(rows)} to {len(rows) - added}.", '',
             f"The baseline contained {summary['correctedPreviouslyContradictoryValidationFlags']} contradictory validation flags on quarantined remuneration records. Those records are included in the retry queue; empty schedules are not counted as validated.", '',
             f"Publishable financial summaries increased from {len(old_financial)} to {len(new_financial)} Nation-years. Some recovered document validations confirm financial summaries that were already available; document recoveries are not all new financial years.", '',
             'The recovery uses native text, separately validated geometric table candidates, and free local OCR. Complete visual transcriptions are bound to the exact PDF hash, source year and URL; all named rows and reported components must reconcile. Explicit PDF covers correct swapped ISC document labels while preserving the listing label and original URL.', '',
             'Numeric official names, footer totals, merged columns, implausible amounts, and non-reconciling rows remain withheld. Missing values and unidentified officials are not invented. Some files still require source or accounting review after bounded OCR.', '',
             'Saskatchewan source records and financial summaries are unchanged.', '',
             '| Nation | Year | Document | Result |', '|---|---|---|---|']
    if result.get('latestPass'):
        latest = result['latestPass']
        lines[4:4] = [f"Latest pass: {latest['recoveredDocuments']} additional validated documents from a queue of "
                      f"{latest['reviewBefore']}, including {latest['newlyPublishableFinancialYears']} newly publishable financial Nation-years.", '']
    for r in result['documents']:
        source_url = quote(r['sourcePdf'], safe=':/?=&%#+,')
        lines.append(f"| {r['nation']} | {r['year']} | [{r['documentType']}]({source_url}) | {'Recovered' if r['recovered'] else 'Review required'} |")
    lines += ['', 'The JSON companion retains per-document status, identity/year checks, original ISC labels, and warnings.']
    (ROOT / 'alberta-parser-recovery-report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default="ebcf2bb")
    parser.add_argument("--round-baseline", help="Also report recoveries since the preceding parser pass")
    args = parser.parse_args()
    generate(args.baseline, args.round_baseline)
