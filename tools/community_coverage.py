"""Offline four-category coverage inventory. Empty scans never prove no activity."""
import argparse
import csv
import gzip
import json
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
try:
    from tools.jobs_collector import effective_status, validation_warnings, ACTIVE_STATUSES
    from tools.events_discovery import is_publishable_event
except ImportError:
    from jobs_collector import effective_status, validation_warnings, ACTIVE_STATUSES
    from events_discovery import is_publishable_event

ROOT = Path(__file__).resolve().parents[1]


def inventory(root, today, snapshot=None):
    def load(name):
        path = snapshot / (name + '.gz') if snapshot else root / name
        return json.loads(gzip.decompress(path.read_bytes()) if snapshot else path.read_bytes())
    bands = load('data.json')['bands'] if snapshot and (snapshot/'data.json.gz').exists() else json.loads((root / 'data.json').read_text())['bands']
    news, events, jobs, projects = [load(n + '-data.json') for n in ('news', 'events', 'jobs', 'projects')]
    registries = {kind: load(kind + '-sources.json')['communities'] for kind in ('news', 'events')}
    jobs_registry = {str(r['communityId']): r for r in load('jobs-source-registry.json')['communities']}
    research_path=root/'research/community-intelligence/phase2-2026-11-02/source-checks.json'
    research_checks=json.loads(research_path.read_text()) if research_path.exists() and not snapshot else {}
    cutoff = (today - timedelta(days=90)).isoformat()
    cutoff30 = (today - timedelta(days=30)).isoformat()
    result = []
    for band in bands:
        key = str(band['id'])
        nr = [r for r in news['articles'] if str(r.get('bandId')) == key]
        er = [r for r in events['events'] if str(r.get('bandId')) == key and is_publishable_event(r, today)
              and str(r.get('endDate') or r.get('startDate') or '') >= today.isoformat()
              and r.get('eventStatus') not in ('cancelled', 'postponed')]
        jr = [r for r in jobs['listings'] if (str(r.get('communityId')) == key or key in list(map(str, r.get('firstNationIds', []))))
              and r.get('verifiedOfficialSource') and not validation_warnings(r) and effective_status(r, today) in ACTIVE_STATUSES]
        pr = [r for r in projects['projects'] + projects.get('verifiedPartnerships', []) if key in list(map(str, r.get('firstNationIds', [])))]
        sources = []
        for kind, rows in registries.items():
            for community in rows:
                if str(community['bandId']) != key: continue
                for s in community.get('sources', []):
                    if not s.get('monitor', True): continue
                    sources.append({'category': kind, 'url': s['url'], 'name': s.get('name'), 'verification': s.get('status'),
                                    'lastCheck': s.get('lastScanStatus') or ('authorized_api_required' if s.get('adapter')=='facebook' else 'not_checked'),
                                    'lastAttempted':s.get('lastCheckedAt'),
                                    'lastSuccess': s.get('lastSuccessfulScanAt') or s.get('lastSuccess')})
        job_sources = jobs_registry.get(key, {})
        for s in job_sources.get('directSources', []) + job_sources.get('regionalSources', []):
            social='facebook.com' in s['url'] or 'instagram.com' in s['url']
            sources.append({'category': 'jobs', 'url': s['url'], 'name': s.get('name'), 'lastCheck': 'authorized_api_required' if social else s.get('checkStatus'), 'lastSuccess': None if social else s.get('lastChecked')})
        for project in pr:
            for s in project.get('sources', []):
                check=research_checks.get(s['url'],{})
                sources.append({'category':'projects','url':s['url'],'name':s.get('name'),
                    'lastCheck':check.get('status','historical_review'),'lastSuccess':check.get('lastSuccess') or project.get('lastVerifiedAt'),
                    'relationship':project.get('relationshipType','See source-dated project description; ownership not inferred')})
        states={}
        for kind in ('news','events','jobs','projects'):
            checks=[s.get('lastCheck') for s in sources if s['category']==kind]
            states[kind]=('not_registered' if not checks else 'checked' if any(s in {'checked','ok','partial'} for s in checks)
                          else 'source_failure_or_restriction' if any(s not in {None,'not_checked','historical_review','stale'} for s in checks)
                          else 'not_recently_checked')
        recent = sum(cutoff <= str(r.get('publishedAt') or '')[:10] <= today.isoformat() for r in nr)
        counts = {'recentNews90': recent, 'upcomingEvents': len(er), 'verifiedProjects': len(pr), 'activeJobs': len(jr)}
        missing = [k for k, v in counts.items() if not v]
        result.append({'communityId': key, 'communityName': band['name'], 'province': band['province'],
                       'newsCount': len(nr), 'latestNews': max((str(r.get('publishedAt') or '')[:10] for r in nr), default=None),
                       'recentNews30': sum(cutoff30 <= str(r.get('publishedAt') or '')[:10] <= today.isoformat() for r in nr),
                       **counts, 'allFour': not missing, 'noVerifiedInformation': not (nr or er or pr or jr),
                       'missingCategories': missing, 'researchPriority': len(missing), 'sources': sources, 'sourceStateByCategory':states,
                       'emptyResultMeaning': 'No verified records in current inventory; public availability not established' if missing else None})
    province = {}
    for p in ('SK', 'AB', 'MB'):
        rows = [r for r in result if r['province'] == p]
        province[p] = {'tracked': len(rows), **{k: sum(bool(r[k]) for r in rows) for k in
                      ('recentNews30', 'recentNews90', 'upcomingEvents', 'verifiedProjects', 'activeJobs', 'allFour', 'noVerifiedInformation')},
                       'newsRecords': sum(r['newsCount'] for r in rows), 'upcomingEventRecords': sum(r['upcomingEvents'] for r in rows),
                       'projectAssociations': sum(r['verifiedProjects'] for r in rows), 'activeJobAssociations': sum(r['activeJobs'] for r in rows),
                       'sourceStates':{kind:dict(Counter(r['sourceStateByCategory'][kind] for r in rows)) for kind in ('news','events','jobs','projects')}}
    return {'asOf': today.isoformat(), 'byProvince': province, 'communities': sorted(result, key=lambda r: (-r['researchPriority'], r['province'], r['communityName'])),
            'limitations': ['An empty inventory is not proof that no public information exists.', 'Regional employment source coverage does not imply a job in every member Nation.',
                           'Projects describe source-dated evidence, not necessarily current construction status. Audited disclosures alone are excluded from verified project counts.',
                           'Date-unavailable jobs are excluded from confirmed active coverage.']}


def write_report(root, today, baseline):
    after = inventory(root, today)
    before = inventory(root, today, baseline) if baseline else None
    delta=[]
    if baseline:
        for kind,field in [('news','articles'),('events','events'),('projects','projects'),('jobs','listings')]:
            old=json.loads(gzip.decompress((baseline/(kind+'-data.json.gz')).read_bytes()))[field]
            current=json.loads((root/(kind+'-data.json')).read_text())[field]
            old_by_id={r['id']:r for r in old};new_by_id={r['id']:r for r in current}
            for key,row in new_by_id.items():
                if key not in old_by_id or row!=old_by_id[key]:
                    volatile={'lastChecked','lastCheckedAt','contentFingerprint','firstDiscoveredAt','updatedAt','revision','sourceContentSha256','researchEvidence'}
                    material=lambda r:{k:v for k,v in r.items() if k not in volatile}
                    change='added' if key not in old_by_id else 'updated' if material(row)!=material(old_by_id[key]) else 'metadata_checked'
                    delta.append({'category':kind,'change':change,'id':key,
                                  'title':row.get('title') or row.get('name'),'communityIds':row.get('firstNationIds') or [row.get('bandId') or row.get('communityId')],
                                  'sourceUrl':row.get('url') or row.get('sourceUrl') or (row.get('sources') or [{}])[0].get('url'),
                                  'status':effective_status(row,today) if kind=='jobs' else row.get('status'),
                                  'publishedAt':row.get('publishedAt'),'startDate':row.get('startDate')})
            for key in old_by_id.keys()-new_by_id.keys():delta.append({'category':kind,'change':'removed_or_merged','id':key})
    payload = {'baseline': before, 'current': after,'recordChanges':delta}
    (root / 'community-coverage-report.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
    lines = ['# Four-category community coverage', '', f'As of {today.isoformat()}. Counts are Nations with verified records; activity is not inferred from registered sources.', '',
             '| Province | Tracked | News ≤90 days | Upcoming events | Projects/partnerships | Active jobs | All four | No verified information |',
             '|---|---:|---:|---:|---:|---:|---:|---:|']
    for p, r in after['byProvince'].items():
        def val(k): return f"{before['byProvince'][p][k]} → {r[k]}" if before else str(r[k])
        lines.append(f"| {p} | {r['tracked']} | {val('recentNews90')} | {val('upcomingEvents')} | {val('verifiedProjects')} | {val('activeJobs')} | {val('allFour')} | {val('noVerifiedInformation')} |")
    lines += ['', *['- ' + s for s in after['limitations']], '', 'Complete community-level inventory, source checks, and record changes: `community-coverage-report.json` and `.csv`.']
    if delta:
        lines += ['', '## Record changes', '', '| Category | Added records | Materially updated | Check metadata only | Removed/merged |','|---|---:|---:|---:|---:|']
        for kind in ('news','events','projects','jobs'):
            counts=Counter(r['change'] for r in delta if r['category']==kind)
            lines.append(f"| {kind} | {counts['added']} | {counts['updated']} | {counts['metadata_checked']} | {counts['removed_or_merged']} |")
        lines += ['', 'Added job candidates include held and closed postings; only confirmed active jobs contribute to coverage above. Shared projects are counted once as records and separately as community associations.']
    (root / 'community-coverage-report.md').write_text('\n'.join(lines) + '\n')
    with (root / 'community-coverage-report.csv').open('w') as f:
        fields = ['communityId', 'communityName', 'province', 'newsCount', 'latestNews', 'recentNews30', 'recentNews90', 'upcomingEvents', 'verifiedProjects', 'activeJobs', 'allFour', 'noVerifiedInformation', 'missingCategories']
        w = csv.DictWriter(f, fields, extrasaction='ignore'); w.writeheader(); w.writerows(after['communities'])
    return payload


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--root', type=Path, default=ROOT); p.add_argument('--today', type=date.fromisoformat, default=date.today())
    p.add_argument('--baseline', type=Path); a = p.parse_args()
    print(json.dumps(write_report(a.root, a.today, a.baseline)['current']['byProvince'], indent=2))
