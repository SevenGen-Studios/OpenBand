"""Immutable, province-scoped preservation fingerprints for Manitoba ingestion."""
import hashlib
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
# Independently maintained community feeds are not financial/profile invariants.
MUTABLE_COMMUNITY_FEEDS = {'news-data.json','projects-data.json','jobs-data.json'}
FILES = ['data.json','capital-data.json','member-counts.json','map-data.json','contacts-data.json','first-nation-logos.json','first-nation-logo-report.json','community-enterprise.json','news-data.json','projects-data.json','jobs-data.json','elections-data.json']
def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
def snapshot(root=ROOT):
    data = json.loads((root/'data.json').read_text())
    protected = {str(b['id']) for b in data['bands'] if b.get('province') in ('SK','AB')}
    result = {'protectedIds':sorted(protected), 'provinceCounts':{code:sum(b.get('province')==code for b in data['bands']) for code in ('SK','AB')},'files':{}}
    keys = {'data.json':('bands','id'), 'capital-data.json':('bands',None),'member-counts.json':('bands',None),'map-data.json':('communities','id'),'contacts-data.json':('contacts','nation_id'),'first-nation-logos.json':('logos','nation_id')}
    for filename in FILES:
        path=root/filename
        if not path.exists():continue
        value=json.loads(path.read_text())
        if filename in keys:
            key,idkey=keys[filename];rows=value[key]
            selected={str(k):v for k,v in rows.items() if str(k) in protected} if idkey is None else [r for r in rows if str(r.get(idkey)) in protected]
        elif filename=='community-enterprise.json':
            selected={**value,'coverage':[r for r in value.get('coverage',[]) if str(r.get('bandId')) in protected]}
        elif filename=='first-nation-logo-report.json':selected=[r for r in value if str(r.get('nation_id')) in protected]
        else:selected=value
        result['files'][filename]=digest(selected)
    return result

def verify(baseline, root=ROOT):
    actual=snapshot(root)
    def protected(value):
        return {**value,'files':{k:v for k,v in value['files'].items() if k not in MUTABLE_COMMUNITY_FEEDS}}
    if protected(actual) != protected(baseline):
        raise ValueError('Protected Saskatchewan/Alberta data changed: '+', '.join(k for k,v in actual['files'].items() if k not in MUTABLE_COMMUNITY_FEEDS and v != baseline['files'].get(k)))
    return actual
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--create',action='store_true');a=p.parse_args()
    path=ROOT/'tools/manitoba-source-cache/protected-baseline.json'
    if a.create:
        if path.exists():raise SystemExit('Baseline already exists; refusing to overwrite')
        path.write_text(json.dumps(snapshot(),indent=2)+'\n')
    else:verify(json.loads(path.read_text()));print('All protected SK/AB record fingerprints unchanged')
