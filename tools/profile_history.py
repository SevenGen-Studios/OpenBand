"""Render citation-backed profile history from history-data.json for static and live views."""
from datetime import date
from html import escape
import json
from urllib.parse import urlsplit


def render_history(record, bands, slugify):
    sources = {s['id']: s for s in record['historical_sources']}
    profiles = {str(b['id']): b for b in bands}
    used = set()

    def url(value):
        return escape(value, quote=True) if urlsplit(value).scheme == 'https' and urlsplit(value).netloc else ''

    def citations(ids):
        used.update(ids)
        return ''.join(f' <a class="history-citation" href="{url(sources[i]["url"])}" target="_blank" rel="noopener" aria-label="Source: {escape(sources[i]["title"], quote=True)}">[{list(sources).index(i) + 1}]</a>' for i in ids)

    def fact(label, key):
        value = record[key]
        if isinstance(value, list):
            value = ', '.join(value)
        if key == 'treaty_signing_date':
            d = date.fromisoformat(value)
            value = f'{d:%B} {d.day}, {d.year}'
        return f'<div><dt>{label}</dt><dd>{escape(value)}{citations(record["fact_source_ids"][key])}</dd></div>'

    def profile_link(profile_id, label=None):
        band = profiles.get(str(profile_id))
        if not band:
            return escape(label or '')
        return f'<a href="/first-nations/{slugify(band["name"])}/">{escape(label or band["name"])}</a>'

    overview = ' '.join(escape(p['text']) + citations(p['source_ids']) for p in record['historical_overview'])
    primary = ''.join(fact(label, key) for label, key in [
        ('Treaty', 'treaty_number'), ('Signing date', 'treaty_signing_date'),
        ('Signing location', 'treaty_signing_location'), ('Historical Chief', 'historical_chiefs')])
    secondary = ''.join(fact(label, key) for label, key in [
        ('Historical Headmen', 'historical_headmen'), ('Treaty Commissioner', 'treaty_commissioner'),
        ('Traditional language', 'traditional_language'), ('Historical territory', 'traditional_territory'),
        ('Land claim settlement', 'land_claim_settlement')])
    events = ''.join(f'<p><strong>{escape(e["date"])} · {escape(e["title"])}</strong> — {escape(e["description"])}{citations(e["source_ids"])}</p>' for e in record['significant_historical_events'])
    notes = ''.join(f'<p class="history-note">{escape(n["text"])}{citations(n["source_ids"])}</p>' for n in record.get('research_notes', []))
    connections = ''
    for c in record['historical_connections']:
        name = profile_link(c['target_profile_id'], c['name']) if c.get('target_profile_id') else escape(c['name'])
        label = 'Historical band' if c['entity_type'] == 'historical_band' else 'Present-day First Nation'
        related = ' · '.join(profile_link(i) for i in c.get('related_profiles', []))
        connections += f'<li><h5>{name} <span>{label}</span></h5><p>{escape(c["description"])}{citations(c["source_ids"])}</p>' + (f'<p class="history-related">Present-day profiles: {related}</p>' if related else '') + '</li>'
    verified = record.get('verification_status') == 'verified' and bool(record.get('last_verified_date')) and bool(used) and all(sources[i].get('verification_status') == 'checked' and sources[i].get('last_checked_date') for i in used)
    badge = f'<span class="history-verified" title="Cited sources checked {escape(record["last_verified_date"], quote=True)}">Sources Verified</span>' if verified else ''
    return (
        '<section class="history-card" aria-label="Brief History">'
        '<div class="history-heading"><h3><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M12 5v15M12 5C8 2 4 3 2 4v15c3-1 7-1 10 1 3-2 7-2 10-1V4c-2-1-6-2-10 1Z"/></svg>Brief History</h3>'
        f'{badge}</div><p class="history-overview">{overview}</p><dl class="history-facts">{primary}</dl>'
        f'<details class="history-more"><summary>Read More <span>Leaders, territory, events &amp; historical connections</span></summary><dl class="history-facts history-facts-secondary">{secondary}</dl>{events}{notes}'
        f'<div class="history-connections"><h4>Historical Connections</h4><ul>{connections}</ul><p class="history-note">{escape(record["connections_note"])}</p></div>'
        '</details></section>'
    )


def build_history(root, bands, slugify):
    data = json.loads((root / 'history-data.json').read_text(encoding='utf-8'))
    markup = {str(r['band_number']): render_history(r, bands, slugify) for r in data['records']}
    (root / 'assets' / 'profile-history.js').write_text(
        '// Generated from history-data.json by tools/build_site.py. Do not edit.\n'
        'window.OPENBAND_HISTORY=' + json.dumps(markup, ensure_ascii=False).replace('<', '\\u003c') + ';\n', encoding='utf-8')
    return markup
