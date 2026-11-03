"""Compare the public directory with identity-checked ISC provincial rosters."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'research/band-numbers/2026-11-03'


def audit(bands, rosters):
    provinces = {}
    for province, roster in rosters.items():
        rows = [band for band in bands if band.get('province') == province]
        numbers = {band.get('iscBandNumber') for band in rows}
        missing = []
        administrations = []
        for nation in roster['nations']:
            number = nation['iscBandNumber']
            if number in numbers:
                continue
            # ISC lists the Stoney umbrella alongside its three governments.
            linked = [band['id'] for band in rows if any('BAND_NUMBER=471&' in source.get('url', '') for source in band.get('relatedDisclosureSources', []))]
            if province == 'AB' and number == 471 and set(linked) == {433, 473, 475}:
                administrations.append({**nation, 'representedByNationIds': linked, 'reason': 'Shared Stoney administration; individual Nations have separate profiles and financial totals.'})
            else:
                missing.append(nation)
        provinces[province] = {
            'profileCount': len(rows), 'officialRosterCount': len(roster['nations']),
            'uniqueVerifiedBandNumbers': len(numbers - {None}),
            'missingOfficialNations': missing,
            'sharedAdministrations': administrations,
            'regionalCommunities': [{'id': row['id'], 'name': row['name'], 'iscBandNumber': row.get('iscBandNumber')} for row in rows if row.get('rosterScope') == 'regional_listing'],
        }
    return {'provinces': provinces, 'completeOfficialCoverage': all(not p['missingOfficialNations'] for p in provinces.values())}


if __name__ == '__main__':
    bands = json.loads((ROOT / 'data.json').read_text(encoding='utf-8'))['bands']
    rosters = json.loads((EVIDENCE / 'provincial-rosters.json').read_text(encoding='utf-8'))
    report = audit(bands, rosters)
    (ROOT / 'provincial-roster-audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    for province, result in report['provinces'].items():
        print(f"{province}: {result['profileCount']} profiles; {len(result['missingOfficialNations'])} missing official Nations")
    raise SystemExit(not report['completeOfficialCoverage'])
