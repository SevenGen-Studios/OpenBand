"""Apply reviewed research with archived primary-source evidence, never count leads."""
import gzip
import hashlib
import json
from datetime import date
from pathlib import Path
try:
    from tools.community_updates import fold, track_changes
    from tools.news_discovery import write_json, canonical_url, article_page_metadata
    from tools.events_discovery import is_publishable_event, explicit_event_dates
    from tools.jobs_collector import normalize_listing, validation_warnings
    from tools.research_public_sources import evidence_text
except ImportError:
    from community_updates import fold, track_changes
    from news_discovery import write_json, canonical_url, article_page_metadata
    from events_discovery import is_publishable_event, explicit_event_dates
    from jobs_collector import normalize_listing, validation_warnings
    from research_public_sources import evidence_text

ROOT = Path(__file__).resolve().parents[1]


def validate(entry, roster, checks, root, today):
    if entry.get('reviewStatus') != 'reviewed': raise ValueError('Research leads cannot be published')
    record = entry['record']; kind = entry['kind']
    ids = record.get('firstNationIds') or [record.get('bandId') or record.get('communityId')]
    if not ids or not set(map(str, ids)).issubset(roster): raise ValueError('Unknown community identity')
    if not entry.get('evidence'): raise ValueError('Missing primary-source evidence')
    texts = []
    for proof in entry['evidence']:
        check = proof if proof.get('evidencePath') and proof.get('sha256') else checks.get(proof['url'], {})
        if check.get('status') != 'checked': raise ValueError('Source was not successfully checked')
        body = gzip.decompress((root / check['evidencePath']).read_bytes())
        if hashlib.sha256(body).hexdigest() != check['sha256']: raise ValueError('Evidence digest mismatch')
        text = evidence_text(root, check)
        if not proof.get('terms') or not all(fold(term) in fold(text) for term in proof['terms']):
            raise ValueError('Reviewed assertions not found in source')
        texts.append(text)
    association=entry.get('communityEvidence',{})
    if set(association)!=set(map(str,ids)) or any(not names or not any(fold(n) in fold(' '.join(texts)) for n in names) for names in association.values()):
        raise ValueError('Explicit community evidence does not match record associations')
    if kind == 'projects':
        if not record.get('relationshipType'): raise ValueError('Project ownership/beneficiary role must be explicit')
        if record.get('ownershipPercentage') is not None and not entry.get('ownershipEvidence'):
            raise ValueError('Ownership percentage requires separate reviewed evidence')
        if record.get('status') and not record.get('statusAsOf'): raise ValueError('Status needs an evidence date')
        if record.get('status') and entry.get('statusEvidence') != {'status':record['status'],'asOf':record['statusAsOf']}:
            raise ValueError('Project status differs from the reviewed source-dated claim')
    elif kind == 'jobs':
        if not record.get('activeEvidence') or not record.get('verifiedOfficialSource'): raise ValueError('No active listing evidence')
        normalized = normalize_listing(record, today)
        if validation_warnings(normalized): raise ValueError('Job fails publication gate')
        if not record.get('closingDate') and 'open until filled' not in ' '.join(texts).lower():
            raise ValueError('Undated jobs require explicit open-until-filled evidence')
    elif kind == 'news':
        if not record.get('publishedAt') or str(record['publishedAt']) > today.isoformat(): raise ValueError('Unverified publication date')
        # Publication metadata is independent of event dates and page-modified dates.
        proof = entry['evidence'][0]
        check = proof if proof.get('evidencePath') else checks[proof['url']]
        markup = gzip.decompress((root / check['evidencePath']).read_bytes()).decode('utf-8', errors='replace')
        metadata = article_page_metadata(markup, check['url'])
        if metadata.get('published') != record['publishedAt']: raise ValueError('Publication metadata absent or mismatched')
    elif kind == 'events':
        if not is_publishable_event(record, today): raise ValueError('Event fails publication gate')
        dates={d for pair in explicit_event_dates(record.get('description','')) for d in pair if d}
        if record['startDate'] not in dates: raise ValueError('Event start differs from explicit reviewed date')
    else: raise ValueError('Unknown dataset')


def apply(root=ROOT, today=None, report_path=None):
    today = today or date.today()
    roster = {str(b['id']) for b in json.loads((root / 'data.json').read_text())['bands']}
    entries = json.loads((root / 'community-enrichment.json').read_text())['records']
    checks = json.loads((root / 'research/community-intelligence/phase2-2026-11-02/source-checks.json').read_text())
    payloads = {k: json.loads((root / (k + '-data.json')).read_text()) for k in ('news', 'events', 'projects')}
    overrides = json.loads((root / 'jobs-overrides.json').read_text())
    outcome = []
    for entry in entries:
        validate(entry, roster, checks, root, today)
        kind = entry['kind']; row = dict(entry['record'])
        rows = overrides.setdefault('manualListings', []) if kind == 'jobs' else payloads[kind][{'news': 'articles', 'events': 'events', 'projects': 'projects'}[kind]]
        if any(r['id'] == row['id'] for r in rows):
            outcome.append({'kind': kind, 'id': row['id'], 'action': 'existing_preserved'}); continue
        urls = {canonical_url(e['url']) for e in entry['evidence']}
        row_ids = set(map(str, row.get('firstNationIds') or [row.get('bandId') or row.get('communityId')]))
        duplicate = next((r for r in rows if set(map(str, r.get('firstNationIds') or [r.get('bandId') or r.get('communityId')])) == row_ids
                         and fold(r.get('name') or r.get('title')) == fold(row.get('name') or row.get('title'))
                         and urls.intersection({canonical_url(r.get('url') or r.get('sourceUrl') or '')} | {canonical_url(s['url']) for s in r.get('sources', [])})), None)
        if duplicate:
            outcome.append({'kind': kind, 'id': row['id'], 'action': 'duplicate_suppressed', 'existingId': duplicate['id']}); continue
        row['researchEvidence'] = [{'url': e['url'], 'sha256': e.get('sha256') or checks[e['url']]['sha256'],
                                   'evidencePath': e.get('evidencePath') or checks[e['url']]['evidencePath'],
                                   'checkedAt': e.get('lastSuccess') or checks[e['url']]['lastSuccess']} for e in entry['evidence']]
        if kind == 'jobs': row['manualOverride'] = True
        rows.append(row); outcome.append({'kind': kind, 'id': row['id'], 'action': 'added'})
    for kind, data in payloads.items():
        if kind == 'projects': data['generatedAt'] = today.isoformat()
        else:
            field = 'articles' if kind == 'news' else 'events'
            data['articleCount' if kind == 'news' else 'eventCount'] = len(data[field])
        write_json(root / (kind + '-data.json'), data)
    write_json(root / 'jobs-overrides.json', overrides)
    report_path=report_path or root / 'research/community-intelligence/phase2-2026-11-02/backfill-results.json'
    previous=json.loads(report_path.read_text()) if report_path.exists() else {}
    history=previous.get('firstAppliedRecords') or previous.get('records') or []
    history_by_id={(r['kind'],r['id']):r for r in history}
    for r in outcome:history_by_id.setdefault((r['kind'],r['id']),r)
    write_json(report_path, {'asOf': today.isoformat(), 'records': outcome, 'firstAppliedRecords':list(history_by_id.values())})
    return outcome


if __name__ == '__main__':
    from collections import Counter
    print(dict(Counter((r['kind'], r['action']) for r in apply())))
