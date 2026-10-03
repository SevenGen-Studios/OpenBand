"""Retry failed Alberta OCR with recognition separated from large dataset merges."""
from copy import deepcopy
from tools.ingest_alberta import ROOT, read, write, bounded_parse, should_preserve_remuneration
from tools.capital_parser import save_summary


def main():
    data = read(ROOT / 'data.json')
    targets = [(band, filing) for band in data['bands'] if band.get('province') == 'AB'
               for filing in band.get('filings', []) if filing.get('posted') and filing.get('href')
               and (filing.get('verificationStatus') != 'automated_validated' or filing.get('manual_review_required'))
               and (str(filing.get('ocrStatus', '')).startswith('error')
                    or filing.get('verificationStatus') in {'parse_timeout_or_error', 'retrieval_or_parse_error'}
                    or filing.get('verificationStatus') == 'automated_validated' and filing.get('manual_review_required'))]
    results = []
    for index, (band, filing) in enumerate(targets, 1):
        identity = {key: deepcopy(band[key]) for key in ('id', 'name', 'officialName', 'aliases') if key in band}
        result = bounded_parse((identity, deepcopy(filing), True))
        results.append((band, filing, result))
        print(f"[{index}/{len(targets)}] {band['name']} {filing['year']}: {result[2].get('parse_status')}", flush=True)
    # Recognition workers have exited before the large financial JSON is loaded.
    capital = read(ROOT / 'capital-data.json')
    for band, filing, (bid, url, update, summary) in results:
        existing = capital.get('bands', {}).get(bid, {}).get('years', {}).get(filing['year'])
        preserve_capital = bool(summary and existing and existing.get('publishable') and not summary.get('publishable'))
        if preserve_capital or should_preserve_remuneration(filing, update):
            if preserve_capital and filing.get('verificationStatus') != 'automated_validated':
                filing.update({key: value for key, value in update.items() if key not in
                               ('people', 'docType', 'documentTitle', 'listedDocType', 'listedDocumentTitle')})
            filing['lastReparseAttempt'] = update.get('lastChecked')
            filing['reparseWarnings'] = update.get('warnings', [])
            filing['reparseStatus'] = update.get('parse_status')
        else:
            filing.update(update)
            if summary:
                save_summary(capital, band, filing, summary)
    write(ROOT / 'data.json', data)
    write(ROOT / 'capital-data.json', capital)


if __name__ == '__main__':
    main()
