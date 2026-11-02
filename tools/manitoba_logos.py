"""Apply only visually reviewed, hash-bound Manitoba logo approvals.

Discovery/ranking is research, never approval. Reapply with --apply; optionally
use --asset-cache containing BAND_ID.source files for an offline review replay.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path

from tools.collect_first_nation_logos import ROOT, request_bytes, save_asset_payload

REVIEW_PATH = ROOT / 'manual_overrides/manitoba-logo-reviews.json'
LOGO_FIELDS = ('logo_url', 'logo_source', 'logo_asset_source', 'logo_verified', 'logo_status')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def nonbranding(data):
    projection = copy.deepcopy(data)
    for band in projection['bands']:
        if band.get('province') == 'MB':
            for key in LOGO_FIELDS:
                band.pop(key, None)
    return projection


def approved_review(review, band, payload):
    if band.get('province') != 'MB' or str(review['nation_id']) != str(band['id']):
        raise ValueError('Logo review belongs to a different Nation/province')
    if review.get('nation_name') != band['name'] or review.get('visually_verified') is not True:
        raise ValueError('Explicit named visual review required')
    if not review.get('verification_note') or not review.get('identity_evidence'):
        raise ValueError('Visual and source identity evidence required')
    if hashlib.sha256(payload).hexdigest() != review['source_sha256']:
        raise ValueError('Original asset changed; visual review must be repeated')
    return True


def apply(asset_cache=None):
    from tools.ingest_manitoba import dataset_lock
    with dataset_lock():
        data = json.loads((ROOT / 'data.json').read_text())
        original = digest(nonbranding(data))
        registry = json.loads((ROOT / 'first-nation-logos.json').read_text())
        report = json.loads((ROOT / 'first-nation-logo-report.json').read_text())
        reviews = json.loads(REVIEW_PATH.read_text())
        bands = {str(b['id']): b for b in data['bands']}
        logos = {str(r['nation_id']): r for r in registry['logos']}
        details = {str(r['nation_id']): r for r in report}
        for review in reviews['approvals']:
            key = str(review['nation_id']);band = bands[key]
            if asset_cache:
                payload = (Path(asset_cache) / f'{key}.source').read_bytes()
            else:
                payload, _, _ = request_bytes(review['asset_url'])
            approved_review(review, band, payload)
            logo = save_asset_payload(band, review['page_url'], review['asset_url'], review['source_kind'], payload, review['content_type'])
            logo.update(verification_note=review['verification_note'], source_sha256=review['source_sha256'],
                        source_page_sha256=review['page_sha256'], identity_evidence=review['identity_evidence'],
                        visual_review={'method':'Source asset visually inspected; Nation identity compared with the attributable source page',
                                       'reviewed_at':review['reviewed_at'], 'review_sha256':digest(review)})
            logos[key] = logo
            details[key] = {'nation_id':band['id'], 'nation_name':band['name'], 'status':'verified',
                            'source':logo['logo_source'], 'asset':logo['logo_asset_source'],
                            'reason':logo['verification_note'], 'sha256':logo['sha256'],
                            'source_sha256':logo['source_sha256'], 'visual_review':logo['visual_review']}
            for field in LOGO_FIELDS:
                band[field] = logo[field]
        if digest(nonbranding(data)) != original:
            raise ValueError('Unexpected nonbranding change; refusing dataset write')
        registry['logos'] = [logos[str(r['nation_id'])] for r in registry['logos']]
        registry.update(verifiedCount=sum(bool(r['logo_verified']) for r in registry['logos']))
        registry['unverifiedCount'] = registry['recordCount'] - registry['verifiedCount']
        for name, value in [('first-nation-logos.json',registry),('first-nation-logo-report.json',[details[str(r['nation_id'])] for r in report]),('data.json',data)]:
            target=ROOT/name;temporary=target.with_suffix(target.suffix+'.tmp')
            temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');temporary.replace(target)
    return write_report()


def write_report():
    reviews = json.loads(REVIEW_PATH.read_text())
    registry = json.loads((ROOT/'first-nation-logos.json').read_text())
    searches = {str(r['nation_id']):r for r in reviews['nation_searches']}
    rows=[]
    for logo in registry['logos']:
        key=str(logo['nation_id'])
        if key not in searches:continue
        rows.append({'nation_id':logo['nation_id'],'nation_name':logo['nation_name'],
                     'verified':bool(logo['logo_verified']),'logo_url':logo['logo_url'],
                     'source':logo.get('logo_source'),'asset':logo.get('logo_asset_source'),
                     'research':searches[key]})
    summary={'expectedNations':63,'verifiedLogos':sum(r['verified'] for r in rows),
             'remainingPlaceholders':sum(not r['verified'] for r in rows),'nations':rows}
    (ROOT/'manitoba-logo-report.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    lines=['# Manitoba logo review','',f"Verified: {summary['verifiedLogos']} / 63. Remaining placeholders: {summary['remainingPlaceholders']}.",
           '', 'Only visually inspected, identity-confirmed source assets are approved. Candidate rankings never confer verification.',
           '', '| Nation | Status | Source / remaining review |','|---|---|---|']
    for row in rows:
        note=f"[Source]({row['source']})" if row['verified'] else row['research']['finding']
        lines.append(f"| {row['nation_name']} | {'Verified' if row['verified'] else 'Placeholder'} | {note} |")
    (ROOT/'manitoba-logo-report.md').write_text('\n'.join(lines)+'\n')
    print(f"Manitoba: {summary['verifiedLogos']} verified / 63; {summary['remainingPlaceholders']} placeholders")
    return summary


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--apply',action='store_true');parser.add_argument('--asset-cache');args=parser.parse_args()
    apply(args.asset_cache) if args.apply else write_report()
