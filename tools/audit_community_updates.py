"""Read-only readiness audit; held candidates are not published content."""
import argparse
import json
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
try:
    from jobs_collector import effective_status, validation_warnings, PUBLIC_STATUSES
    from events_discovery import is_publishable_event
except ImportError:
    from tools.jobs_collector import effective_status, validation_warnings, PUBLIC_STATUSES
    from tools.events_discovery import is_publishable_event


def audit(root, today):
    def load(name):
        return json.loads((root / name).read_text(encoding='utf-8'))
    bands = load('data.json')['bands']
    identities = {str(b['id']): b for b in bands}
    news, jobs, events = [load(name) for name in ['news-data.json', 'jobs-data.json', 'events-data.json']]
    problems = []
    for kind, rows, field in [('news', news['articles'], 'bandId'), ('jobs', jobs['listings'], 'communityId'), ('events', events['events'], 'bandId')]:
        ids = [r.get('id') for r in rows]
        if len(set(ids)) != len(ids):
            problems.append({'dataset': kind, 'issue': 'Duplicate record identifiers'})
        for row in rows:
            linked = ([str(row[field])] if row.get(field) else []) + [str(v) for v in row.get('firstNationIds', [])]
            if any(value not in identities for value in linked):
                problems.append({'dataset': kind, 'id': row.get('id'), 'issue': 'Unknown community identifier'})
    public_jobs = [r for r in jobs['listings'] if effective_status(r, today) in PUBLIC_STATUSES]
    for row in public_jobs:
        if validation_warnings(row) or not row.get('verifiedOfficialSource'):
            problems.append({'dataset': 'jobs', 'id': row['id'], 'issue': 'Public listing fails validation'})
    for row in events['events']:
        if not is_publishable_event(row, today):
            problems.append({'dataset': 'events', 'id': row['id'], 'issue': 'Event fails current publication gate'})
    cutoff = (today - timedelta(days=90)).isoformat()
    for row in news['articles']:
        if not str(row.get('url') or '').startswith('https://') or not row.get('publishedAt'):
            problems.append({'dataset': 'news', 'id': row.get('id'), 'issue': 'Missing HTTPS source/publication date'})
    review = load('news-review-queue.json').get('items', [])
    news_reasons = Counter(r.get('reason') or r.get('reviewReason') or r.get('status') or 'Unspecified' for r in review)
    coverage = {}
    for province in sorted({b['province'] for b in bands}):
        ids = {str(b['id']) for b in bands if b['province'] == province}
        coverage[province] = {
            'tracked': len(ids),
            'withNewsLast90Days': len({str(r.get('bandId')) for r in news['articles'] if str(r.get('bandId')) in ids and cutoff <= str(r.get('publishedAt') or '') <= today.isoformat()}),
            'withPublicJobs': len({value for r in public_jobs for value in [str(r.get('communityId') or ''), *map(str, r.get('firstNationIds', []))] if value in ids}),
            'withEvents': len({str(r.get('bandId')) for r in events['events'] if str(r.get('bandId')) in ids}),
        }
    return {'schemaVersion': 1, 'asOf': today.isoformat(), 'trackedCommunities': len(bands), 'byProvince': coverage,
            'news': {'records': len(news['articles']), 'generated': news.get('generated'), 'reviewHistoryRecords': len(review), 'topReviewReasons': dict(news_reasons.most_common(8))},
            'jobs': {'public': len(public_jobs), 'verifiedActive': sum(effective_status(r, today) in {'Open', 'Closing soon'} for r in public_jobs), 'pending': sum(effective_status(r, today) == 'Pending verification' for r in jobs['listings']), 'generated': jobs.get('generated')},
            'events': {'records': len(events['events']), 'generated': events.get('generated')},
            'problems': problems, 'limitations': ['Review history counts include previously held and resolved candidates; they are not a publication backlog count.', 'No listed updates does not establish that a community has no opportunities or events.', 'Facebook discovery requires authorized platform access; source restrictions are not bypassed.']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--today', type=date.fromisoformat, default=date.today())
    args = parser.parse_args()
    result = audit(args.root, args.today)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(1 if result['problems'] else 0)
