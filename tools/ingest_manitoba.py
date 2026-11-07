"""Manitoba discovery and bounded extraction using the existing Alberta engine.

Local changes only. Never commits, pushes, deploys or calls a paid API.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import sys
import tempfile
from contextlib import contextmanager
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools import ingest_alberta as engine
from tools.manitoba_baseline import verify
SOURCE_CACHE=ROOT/'tools/manitoba-source-cache'
BASELINE=SOURCE_CACHE/'protected-baseline.json'

def safe_write(path,value):
    """Preflight preservation, then atomically replace one local dataset."""
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if path.name=='data.json':
        from tools.financial_entry import replay_managed
        replay_managed(value)
    protected=json.loads(BASELINE.read_text())
    if path.name in protected['files']:
        from tools.manitoba_baseline import digest
        protected_ids=set(protected['protectedIds'])
        keys={'data.json':('bands','id'),'capital-data.json':('bands',None),'member-counts.json':('bands',None),'map-data.json':('communities','id'),'contacts-data.json':('contacts','nation_id'),'first-nation-logos.json':('logos','nation_id')}
        if path.name=='data.json' and {str(b['id']) for b in value['bands'] if b.get('province') in ('SK','AB')}!=protected_ids:raise ValueError('Protected province identifiers changed')
        if path.name in keys:
            key,idkey=keys[path.name];rows=value[key]
            selected={str(k):v for k,v in rows.items() if str(k) in protected_ids} if idkey is None else [r for r in rows if str(r.get(idkey)) in protected_ids]
        elif path.name=='community-enterprise.json':
            selected={**value,'coverage':[r for r in value.get('coverage',[]) if str(r.get('bandId')) in protected_ids]}
        elif path.name=='first-nation-logo-report.json':selected=[r for r in value if str(r.get('nation_id')) in protected_ids]
        else:selected=value
        if digest(selected)!=protected['files'][path.name]:raise ValueError('Protected SK/AB records would change: '+path.name)
    with tempfile.NamedTemporaryFile(mode='w',dir=path.parent,prefix='.'+path.name,suffix='.tmp',delete=False,encoding='utf-8') as handle:
        json.dump(value,handle,ensure_ascii=False,indent=None if path.name=='capital-data.json' else 2,separators=(',',':') if path.name=='capital-data.json' else None)
        handle.write('\n');handle.flush();os.fsync(handle.fileno());temporary=handle.name
    os.replace(temporary,path)

def configure():
    engine.PROVINCE='MB';engine.CACHE=ROOT/'.openband-ocr/manitoba'
    engine.SOURCE_CACHE=SOURCE_CACHE;engine.ROSTER_PATH=ROOT/'manitoba-nations.json'
    engine.WORKER_SCRIPT=Path(__file__).resolve()
    engine.PARSER_REVISION='manitoba-20261101-v2-'+ 'alberta-20261009-v28'
    engine.write=safe_write
    from tools import manitoba_source_formats
    engine.download=manitoba_source_formats.download
    engine.NON_PDF_ADAPTER=manitoba_source_formats.parse_non_pdf


def merge_band(data, incoming):
    if incoming.get('province')!='MB':raise ValueError('Only Manitoba records may enter this merge')
    existing=next((b for b in data['bands'] if str(b['id'])==str(incoming['id'])),None)
    if existing and existing.get('province')!='MB':raise ValueError('Band ID collision with protected province')
    if str(incoming['id'])!=str(incoming['iscBandNumber']):raise ValueError('Unverified Manitoba identity mapping')
    merged=deepcopy(existing or {})
    merged.update({k:v for k,v in incoming.items() if v is not None and k!='filings'})
    old={engine.canonical_url(f['href']):deepcopy(f) for f in (existing or {}).get('filings',[]) if f.get('href')}
    for filing in incoming.get('filings',[]):
        key=engine.canonical_url(filing['href'])
        if key not in old:old[key]=filing
        else:old[key].update({k:v for k,v in filing.items() if k in ('retrievedAt','date','sourceListingUrl')})
    merged['aliases']=sorted(set((existing or {}).get('aliases',[])+incoming.get('aliases',[]))-{merged['name']})
    merged['sources']=list({(source['field'],source['url']):source for source in (existing or {}).get('sources',[])+incoming.get('sources',[])}.values())
    merged['filings']=list(old.values())
    merged['discoveryStatus']='error' if any(e['kind']=='filings' for e in incoming.get('sourceErrors',[])) else incoming.get('discoveryStatus',merged.get('discoveryStatus','not_checked'))
    if existing:existing.clear();existing.update(merged)
    else:data['bands'].append(merged)
    data['band_count']=len(data['bands'])
    return merged


def discover(refresh=False,limit=0,workers=2):
    registry=engine.read(engine.ROSTER_PATH);data=engine.read(ROOT/'data.json')
    seeds=registry['nations']
    # Each successful Nation is saved independently; reruns use cached sources.
    if limit:seeds=seeds[:limit]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending={pool.submit(engine.discover_one,seed,refresh):seed for seed in seeds}
        for future in as_completed(pending):
            incoming=future.result();band=merge_band(data,incoming)
            data['generated']=engine.now();safe_write(ROOT/'data.json',data)
            engine.integrate_profiles(data,[band])
    verify(engine.read(BASELINE))


@contextmanager
def dataset_lock():
    """OS lock releases after crashes; parser child tasks do not write datasets."""
    lock=ROOT/'.openband-ocr/manitoba/writer.lock';lock.parent.mkdir(parents=True,exist_ok=True)
    with lock.open('a+b') as handle:
        try:
            if os.name=='nt':
                import msvcrt
                handle.seek(0);handle.write(b'0');handle.flush();handle.seek(0)
                msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as error:raise RuntimeError('Another Manitoba dataset writer is running') from error
        try:yield
        finally:
            if os.name=='nt':
                handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(handle,fcntl.LOCK_UN)


def ocr_attempted(filing,backend=''):
    """A retry with a different local engine is a distinct recovery attempt."""
    desired={'vision':'macos_vision','rapidocr':'rapidocr','windows':'windows_with_rapidocr_crosscheck'}.get(backend,backend)
    records=list(filing.get('ocrAttemptHistory',[]))+[filing]
    if not desired:return any(r.get('ocrRequested') or r.get('ocrStatus') for r in records)
    return any(r.get('ocrEngine')==desired and bool(r.get('ocrStatus')) and r.get('ocrStatus') not in ('not_required_native_text','not_required_reviewed_source') or r.get('ocrRequested') and r.get('ocrRequestedEngine')==backend for r in records)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for flag in ('refresh-roster','integrate-roster','discover','refresh','parse','ocr','retry','reparse','audit','scans-only','unattempted-ocr','timeouts-only'):p.add_argument('--'+flag,action='store_true')
    p.add_argument('--limit',type=int,default=0);p.add_argument('--workers',type=int,choices=range(1,5),default=1)
    p.add_argument('--document-type',choices=['all','audited','remuneration'],default='all')
    p.add_argument('--native-timeout',type=int,choices=[45,90,120,180],default=45)
    p.add_argument('--band-id',action='append',default=[]);p.add_argument('--year')
    p.add_argument('--task');p.add_argument('--result');args=p.parse_args();configure()
    engine.NATIVE_TIMEOUT=args.native_timeout
    engine.TASK_FILTER=lambda band,filing:(not args.band_id or str(band['id']) in args.band_id) and (not args.year or filing['year']==args.year) and (not args.timeouts_only or filing.get('verificationStatus')=='parse_timeout_or_error') and (not args.scans_only or filing.get('requiresOcr') is True) and (not args.unattempted_ocr or not ocr_attempted(filing,os.getenv('OPENBAND_OCR_ENGINE','')))
    if args.task:safe_write(args.result,engine.parse_one(engine.read(args.task)));return
    with dataset_lock():
        if args.refresh_roster:
            from tools.refresh_manitoba_roster import build
            build(args.refresh)
        if args.integrate_roster:
            data=engine.read(ROOT/'data.json')
            for seed in engine.read(engine.ROSTER_PATH)['nations']:merge_band(data,seed)
            safe_write(ROOT/'data.json',data);engine.integrate_profiles(data,[b for b in data['bands'] if b.get('province')=='MB'])
        if args.discover:discover(args.refresh,args.limit,args.workers)
        if args.parse:engine.parse_documents(args.limit,args.workers,args.ocr,args.retry,args.reparse,args.document_type)
        if args.audit:
            from tools.audit_manitoba import audit
            audit()
if __name__=='__main__':main()
