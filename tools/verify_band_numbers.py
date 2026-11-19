"""Verify database identifiers against a saved official ISC roster.

Run from the repository root. The dated report records the reviewed name
variants; new or renamed records are flagged instead of guessed.
"""
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / 'research/band-numbers/2026-11-03'


def audit(bands, roster, reviewed):
    official = {row['attributes']['BAND_NUMBER']: row['attributes']['BAND_NAME'] for row in roster['features']}
    issues, groups, verified = [], defaultdict(list), set()
    for band in bands:
        number = band.get('iscBandNumber')
        expected = reviewed.get(str(band['id']))
        if not isinstance(number, int) or isinstance(number, bool) or number not in official:
            issues.append({'id': band['id'], 'name': band['name'], 'reason': 'Missing or unknown ISC band number'})
            continue
        if not expected or (band['name'], number, official[number]) != (expected['name'], expected['iscBandNumber'], expected['iscName']):
            issues.append({'id': band['id'], 'name': band['name'], 'reason': 'Name/number mapping requires verification'})
        else:
            verified.add(str(band['id']))
        groups[number].append(band)
    duplicates = []
    for number, rows in groups.items():
        if len(rows) < 2:
            continue
        documented = all(row.get('sharedIscIdentity') and any(str(other['id']) in map(str, row.get('relatedNationIds', [])) for other in rows if other is not row) for row in rows if str(row['id']) != str(number))
        duplicates.append({'iscBandNumber': number, 'nationIds': [row['id'] for row in rows], 'status': 'documented_shared_identity' if documented else 'requires_verification'})
        if not documented:
            issues.append({'iscBandNumber': number, 'reason': 'Undocumented duplicate band number'})
    return {'recordCount': len(bands), 'verifiedCount': len(verified), 'unmatched': issues, 'duplicates': duplicates}


if __name__ == '__main__':
    bands = json.loads((ROOT / 'data.json').read_text(encoding='utf-8'))['bands']
    roster = json.loads((RESEARCH / 'isc-first-nations.json').read_text(encoding='utf-8'))
    reviewed = json.loads((RESEARCH / 'reviewed-mappings.json').read_text(encoding='utf-8'))
    report = audit(bands, roster, reviewed)
    (ROOT / 'band-number-audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=True))
    raise SystemExit(bool(report['unmatched']))
