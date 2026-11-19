"""Validated, replayable remuneration snapshots produced by the admin backend.

Only the first publication checks the before-image. Replays restore the complete
approved schedule, even when a scraper has replaced its rows. Legacy overrides
run first; managed snapshots run last. No public rendering schema is changed.
"""
import argparse
from copy import deepcopy
import json
import math
from pathlib import Path
import re
from urllib.parse import urlparse

SCHEMA = 'openband-remuneration-v1'
MONEY = ('remuneration', 'travel', 'expenses', 'creditCard', 'otherPayments', 'travelExpenses', 'other', 'total')


def select(data, band_id, year):
    bands = [b for b in data['bands'] if str(b['id']) == str(band_id)]
    if len(bands) != 1:
        raise ValueError('Nation ID is missing or ambiguous')
    band = bands[0]
    candidates = [f for f in band.get('filings', []) if f.get('year') == year and 'remuneration' in str(f.get('docType', '')).lower()]
    posted = [f for f in candidates if f.get('href') and f.get('posted') is not False]
    candidates = posted or candidates
    if len(candidates) > 1:
        raise ValueError('Multiple source schedules: resolve the source identity first')
    return band, candidates[0] if candidates else None


def amount(value):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or abs(value) > 1e10:
        raise ValueError('Amounts must be finite numbers or null')
    return value


def components(row):
    raw = [row.get(k) for k in ('travel', 'expenses', 'creditCard')]
    travel = None if all(v is None for v in raw) else sum(v or 0 for v in raw)
    if travel is None:
        travel = row.get('travelExpenses')
    return [row.get('remuneration'), travel, row.get('otherPayments', row.get('other'))]


def validate(payload):
    if payload.get('schema') != SCHEMA or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', str(payload.get('bandId', ''))):
        raise ValueError('Invalid schema or Nation ID')
    year = payload.get('year', '')
    if not re.fullmatch(r'\d{4}-\d{4}', year) or int(year[5:]) != int(year[:4]) + 1:
        raise ValueError('Invalid fiscal year')
    if payload.get('state') != 'approved' or not payload.get('approvedBy'):
        raise ValueError('An administrator must verify this revision')
    source = payload.get('source') or {}
    url = urlparse(source.get('url', ''))
    if url.scheme != 'https' or url.hostname not in {'services.sac-isc.gc.ca', 'fnp-ppn.aadnc-aandc.gc.ca'} or url.username or url.password or url.port or not re.fullmatch('[a-f0-9]{64}', source.get('sha256', '')) or not str(source.get('pages', '')).strip():
        raise ValueError('Official PDF URL, SHA-256 and page references are required')
    if source.get('identityAndYearConfirmed') is not True or source.get('completeSchedule') is not True:
        raise ValueError('Explicit source verification is required')
    rows = payload.get('people')
    if not isinstance(rows, list) or not 1 <= len(rows) <= 100:
        raise ValueError('One to 100 officials are required')
    identities = set()
    for row in rows:
        if not isinstance(row, dict) or not str(row.get('name') or '').strip() or not str(row.get('role') or '').strip():
            raise ValueError('Official name and position required')
        identity = (str(row['name']).strip().casefold(), str(row['role']).strip().casefold())
        if identity in identities or re.match(r'^(grand\s+)?(sub)?total\b', identity[0]):
            raise ValueError('Duplicate official or total row')
        identities.add(identity)
        for field in MONEY:
            amount(row.get(field))
        months = amount(row.get('months'))
        if months is not None and not 0 <= months <= 12:
            raise ValueError('Months must be between zero and 12')
        parts = components(row)
        total = row.get('total')
        if all(v is not None for v in parts) and total is not None and abs(sum(parts) - total) > 1.01:
            raise ValueError('Reported official total does not reconcile')
    printed = amount(source.get('scheduleTotal'))
    if printed is not None:
        totals = [r.get('total') for r in rows]
        if any(t is None for t in totals) or abs(sum(totals) - printed) > 1.01:
            raise ValueError('Printed schedule total does not reconcile')
    return payload


def apply(data, payload, first_publication=False):
    validate(payload)
    band, filing = select(data, payload['bandId'], payload['year'])
    if band['name'] != payload['band'] or band.get('province', 'SK') != payload['province']:
        raise ValueError('Nation identity changed')
    if first_publication and filing != payload.get('before'):
        raise ValueError('Published schedule changed; reopen and review the correction')
    source = payload['source']
    # The browser percent-encodes spaces in older ISC disclosure links.
    # Normalize that spelling only, leaving all other URL differences significant.
    if filing and filing.get('href') and filing['href'].replace(' ', '%20') != source['url'].replace(' ', '%20'):
        raise ValueError('Source URL changed; resolve revised source before replay')
    if not first_publication and filing and re.fullmatch('[a-f0-9]{64}', str(filing.get('sha256') or '')) and filing['sha256'] != source['sha256']:
        raise ValueError('Source PDF hash changed; review the revised document')
    if filing is None:
        filing = {'year': payload['year'], 'docType': 'Schedule of Remuneration and Expenses'}
        band.setdefault('filings', []).append(filing)
    # A complete before-image and complete resulting rows are retained in Git;
    # applying a patch to fresh scraper rows would lose unchanged officials.
    filing.update(people=deepcopy(payload['people']), href=source['url'], posted=True,
                  sha256=source['sha256'], manual_override=True,
                  parse_status='manual_override', parse_confidence='manual_reviewed',
                  manual_review_required=False, financialEntryRevision=payload['revision'])
    filing['manualSourceReview'] = {
        'year': payload['year'], 'sourcePdf': source['url'], 'sha256': source['sha256'],
        'identityAndYearConfirmed': True, 'completeSchedule': True,
        'pages': source['pages'], 'reviewedBy': payload['approvedBy'],
        'reviewedAt': payload['approvedAt'],
    }
    for row in filing['people']:
        row['sourceReference'] = {**(row.get('sourceReference') or {}),
            'yearValidated': True, 'sourceDocumentSha256': source['sha256'],
            'selectedYear': int(payload['year'][5:]), 'sourcePdf': source['url'], 'pages': source['pages']}
    return 1


def publish(root, draft):
    validate(draft)
    data_path = root / 'data.json'
    data = json.loads(data_path.read_text())
    path = root / 'manual_overrides' / ('zz-admin-' + str(draft['bandId']) + '-' + draft['year'] + '.json')
    if path.exists() and json.loads(path.read_text()).get('revision') == draft['revision']:
        return False  # a duplicate dispatch is harmless
    apply(data, draft, first_publication=True)
    path.write_text(json.dumps(draft, ensure_ascii=False, indent=2) + '\n')
    data_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('draft', type=Path)
    parser.add_argument('--root', type=Path, default=Path('.'))
    args = parser.parse_args()
    print('Published revision' if publish(args.root, json.loads(args.draft.read_text())) else 'Revision already published')


def replay_managed(data, override_dir=None):
    """Protect managed corrections at automated writer boundaries.

    A province-only scraper may temporarily omit other provinces; their overrides
    are replayed after the normal previous-data merge restores those Nations.
    """
    directory = Path(override_dir) if override_dir is not None else Path(__file__).resolve().parents[1] / 'manual_overrides'
    ids = {str(b['id']) for b in data.get('bands', [])}
    for path in sorted(directory.glob('zz-admin-*.json')):
        payload = json.loads(path.read_text())
        if str(payload.get('bandId')) in ids:
            apply(data, payload)
