"""Register reviewed public research sources in the existing scheduled collectors."""
import json
from pathlib import Path
try:
    from tools.news_discovery import write_json, ensure_registry
except ImportError:
    from news_discovery import write_json, ensure_registry

ROOT = Path(__file__).resolve().parents[1]


def register(root=ROOT):
    registry = json.loads((root / 'community-research-sources.json').read_text())
    roster = {str(b['id']): b for b in json.loads((root / 'data.json').read_text())['bands']}
    checks_path = root / 'research/community-intelligence/phase2-2026-11-02/source-checks.json'
    checks = json.loads(checks_path.read_text()) if checks_path.exists() else {}
    aliases = {'262': ['Sagkeeng', 'Sagkeeng Anicinabe Nation'], '273': ['Roseau River Anishinabe First Nation'],
               '343': ['Mosquito First Nation'], '313': ['NCN', 'Nisichawayasihk Cree Nation'], '384': ['Peepeekisis Cree Nation']}
    for source in registry['sources']:
        if not source.get('verifiedAt') or not source['url'].startswith('https://'):
            raise ValueError('Only reviewed HTTPS sources may be registered')
        if not set(source['communityIds']).issubset(roster): raise ValueError('Unknown community association')
    for kind in ('news', 'events'):
        path = root / (kind + '-sources.json'); payload = ensure_registry({'bands':list(roster.values())}, {}, json.loads(path.read_text()))
        communities = {str(c['bandId']): c for c in payload['communities']}
        for source in registry['sources']:
            if kind not in source['categories']: continue
            for key in source['communityIds']:
                c = communities[key]
                c['aliases'] = list(dict.fromkeys(c.get('aliases', []) + aliases.get(key, [])))
                if any(s['url'].rstrip('/') == source['url'].rstrip('/') for s in c['sources']): continue
                c['sources'].append({'name': source['name'], 'url': source['url'], 'type': source['type'],
                    'status': 'verified', 'adapter': 'html', 'official': source['type'] == 'Official First Nation Website', 'monitor': True,
                    'requiresCommunityMention': source.get('requiresCommunityMention', False),
                    'associationCommunityNames': [roster[i]['name'] for i in source['communityIds']],
                    'researchSourceId': source['id'], 'verifiedAt': source['verifiedAt'],
                    'lastSuccess': checks.get(source['url'], {}).get('lastSuccess')})
        write_json(path, payload)
    path = root / 'jobs-sources.json'; payload = json.loads(path.read_text())
    for source in registry['sources']:
        if 'jobs' not in source['categories']: continue
        if any(s['url'].rstrip('/') == source['url'].rstrip('/') and set(map(str,s.get('communityIds',[]))) == set(source['communityIds']) for s in payload['sources']): continue
        payload['sources'].append({'id': 'research-' + source['id'], 'url': source['url'], 'name': source['name'],
            'sourceType': 'official_first_nation' if source['type'] == 'Official First Nation Website' else 'tribal_council',
            'communityIds': source['communityIds'], 'communityNames': [roster[i]['name'] for i in source['communityIds']],
            'verifiedOfficialSource': True, 'autoPublish': False, 'inspectDetails': True, 'scanMedia': True,
            'sameHostOnly': True, 'parser': 'job_link_index', 'researchSourceId': source['id']})
    write_json(path, payload)


if __name__ == '__main__': register()
