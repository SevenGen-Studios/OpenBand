"""Compile manually reviewed research notes into the canonical editorial dataset.

This is an editorial import, not a scraper. Existing Canoe Lake research is retained.
Run from any directory after reviewing research/profile-history/2026-11-03/reviewed.json.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVIEW_DATE = '2026-11-03'


def compile_notes():
    bands = json.loads((ROOT / 'data.json').read_text(encoding='utf-8'))['bands']
    profiles = {str(b['id']): b for b in bands}
    path = ROOT / 'history-data.json'
    canoe = next(r for r in json.loads(path.read_text(encoding='utf-8'))['records']
                 if r['band_number'] == '394')
    canoe['profile_id'] = '394'
    notes = json.loads((ROOT / 'research/profile-history/2026-11-03/reviewed.json').read_text(encoding='utf-8'))
    reviewed = {n['id']: n for n in notes}
    assert len(reviewed) == len(notes), 'Duplicate research IDs'
    assert set(reviewed) | {'394'} == set(profiles), 'Research coverage must match published profiles'

    def primary(note):
        if note.get('source'):
            return ('https://teaching.usask.ca/indigenoussk/import/' + note['source'] + '.php',
                    'University of Saskatchewan — Indigenous Saskatchewan Encyclopedia')
        return note['url'], note.get('publisher') or profiles[note['id']]['name']

    records = [canoe]
    for note in notes:
        band = profiles[note['id']]
        sources = []

        def source(url, publisher, title=None):
            existing = next((s for s in sources if s['url'] == url), None)
            if existing:
                return existing['id']
            sid = 'source-' + str(len(sources) + 1)
            sources.append(dict(id=sid, title=title or f'{band["name"]} — published history and community account',
                                publisher=publisher, url=url,
                                supports='Published account supporting the cited historical summary, facts or relationship.',
                                locator='History / community account; relevant passage in retrieved page or indexed document excerpt',
                                review_method='Reviewed retrieved text or indexed source excerpt',
                                verification_status='checked', last_checked_date=REVIEW_DATE))
            return sid

        ids = [source(*primary(note))]
        for url, publisher in note.get('extra_sources', []):
            ids.append(source(url, publisher, publisher))
        def refs(indexes):
            return [ids[i] for i in indexes]

        connections = []
        for target, description in note.get('connections', []):
            assert target in profiles, f'Unknown connection {target}'
            connections.append(dict(name=profiles[target]['name'], target_profile_id=target,
                                    entity_type='present_day_first_nation',
                                    relationship_type='documented_historical_relationship',
                                    description=description, source_ids=refs(note.get('connection_sources', [0]))))
        context = [dict(text=note['detail'], source_ids=[ids[0]])] if note.get('detail') else []
        context.append(dict(text='This brief covers selected published accounts. Community oral histories and knowledge extend beyond these records.', source_ids=[]))
        records.append(dict(profile_id=note['id'], band_number=str(band['iscBandNumber']),
                            first_nation_name=band['name'],
                            historical_overview=[dict(text=text, source_ids=refs(indexes)) for text, indexes in note.get('source_parts', [(note['summary'], [0])])],
                            key_facts=[dict(label=k, value=v, source_ids=refs(note.get('fact_sources', {}).get(k, [0]))) for k, v in note['facts'].items()],
                            significant_historical_events=[], research_notes=context,
                            historical_connections=connections,
                            connections_note='These links reflect the relationship described by the cited account; each present-day Nation has its own identity and governance.',
                            historical_sources=sources, verification_status='verified',
                            last_verified_date=REVIEW_DATE))
    path.write_text(json.dumps(dict(schema_version=2, records=records), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Compiled {len(records)} independently sourced profile histories.')


if __name__ == '__main__':
    compile_notes()
