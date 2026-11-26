"""Inventory source availability separately from extraction; no network or data mutation."""
import argparse
import gzip
import json
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def inventory(root=ROOT):
    data = json.loads((root / 'data.json').read_text())
    capital = json.loads((root / 'capital-data.json').read_text())['bands']
    today = date.today()
    latest_closed_end = today.year if today.month >= 4 else today.year - 1
    expected_years = [f"{year}-{year+1}" for year in range(2014, latest_closed_end)]
    communities = []
    for band in data['bands']:
        years = capital.get(str(band['id']), {}).get('years', {})
        records = []
        for filing in band.get('filings', []):
            kind = 'capital' if 'audit' in filing.get('docType', '').lower() else 'remuneration' if 'remuneration' in filing.get('docType', '').lower() else None
            if not kind:
                continue
            posted = bool(filing.get('posted') and filing.get('href'))
            summary = years.get(filing['year']) if kind == 'capital' else None
            if not posted:
                state = 'not_indexed_as_posted'
            elif kind == 'capital':
                state = 'publishable_summary' if summary and summary.get('parseStatus') == 'parsed' and summary.get('publishable') is not False else 'posted_without_summary' if not summary else 'posted_summary_needs_review'
            else:
                state = 'posted_without_rows' if not filing.get('people') else 'rows_need_review' if filing.get('manual_review_required') or filing.get('parse_status') in {'manual_review','failed_validation'} else 'extracted_rows'
            records.append({'year':filing['year'], 'kind':kind, 'state':state, 'sourceUrl':filing.get('href'), 'sourceListingUrl':filing.get('sourceListingUrl'), 'extractionStatus':summary.get('parseStatus') if summary else filing.get('parse_status'), 'warnings':summary.get('warnings', []) if summary else filing.get('warnings', [])})
        known = {(row['year'], row['kind']) for row in records}
        for year in expected_years:
            for kind in ('capital', 'remuneration'):
                if (year, kind) not in known:
                    records.append({'year':year, 'kind':kind, 'state':'not_indexed_unknown_availability', 'sourceUrl':None, 'extractionStatus':None, 'warnings':[]})
        published = sum(row.get('parseStatus') == 'parsed' and row.get('publishable') is not False for row in years.values())
        communities.append({'communityId':str(band['id']), 'communityName':band['name'], 'province':band.get('province','SK'), 'publishableCapitalYears':published, 'filings':records})
    provinces = {}
    for province in ['SK','AB','MB']:
        rows = [r for r in communities if r['province'] == province]
        counts = Counter(f"{f['kind']}:{f['state']}" for r in rows for f in r['filings'])
        provinces[province] = {'communities':len(rows), 'communitiesWithoutPublishableCapital':sum(not r['publishableCapitalYears'] for r in rows), 'filingStates':dict(sorted(counts.items()))}
    return {'asOf':date.today().isoformat(), 'limitations':['Inventory of current indexed source links and extraction states; this report does not HTTP-check every source or prove that unindexed files are unavailable.', 'Department-only or otherwise ambiguous documents remain review work, even when their arithmetic can be extracted.', 'Absent category/year pairs are listed as unknown availability, not confirmed not posted. Expected window: 2014–2015 through the latest completed March fiscal year; older indexed records are retained.', 'Counts are filing records or explicit unknown-availability pairs, except named community counts.'], 'byProvince':provinces, 'communities':communities}


def write_report(root=ROOT, output=None):
    result = inventory(root)
    output = output or root / 'research/financial-recovery/2026-11-26-blood'
    output.mkdir(parents=True, exist_ok=True)
    (output / 'financial-coverage.json.gz').write_bytes(gzip.compress((json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode(),mtime=0))
    lines = [f"# Financial source and extraction coverage — {result['asOf']}", '', 'Inventory of indexed sources, not a live availability check. Posted files and validated financial extraction are separate.', '', '| Province | Communities | No publishable capital years | Posted audits without a summary | Posted audits needing review | Posted remuneration without rows | Unindexed pairs (availability unknown) |', '|---|---:|---:|---:|---:|---:|---:|']
    for province, row in result['byProvince'].items():
        c = row['filingStates']
        lines.append(f"| {province} | {row['communities']} | {row['communitiesWithoutPublishableCapital']} | {c.get('capital:posted_without_summary',0)} | {c.get('capital:posted_summary_needs_review',0)} | {c.get('remuneration:posted_without_rows',0)} | {c.get('capital:not_indexed_unknown_availability',0)+c.get('remuneration:not_indexed_unknown_availability',0)} |")
    lines += ['', '## Community priorities', '', 'Nations with no publishable capital year:']
    lines += [f"- {r['communityName']} ({r['province']}, ID {r['communityId']})" for r in result['communities'] if not r['publishableCapitalYears']]
    lines += ['', '## Limitations', *['- '+line for line in result['limitations']]]
    (output / 'financial-coverage.md').write_text('\n'.join(lines)+'\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    print(json.dumps(write_report(args.root,args.output)['byProvince'],indent=2))
