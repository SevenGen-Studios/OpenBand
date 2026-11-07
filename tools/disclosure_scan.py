"""Scan every database profile for stale ISC filing availability.

Only public document metadata is reconciled. Financial values, parsed people,
and already indexed source documents are preserved. No OCR approval is implied.
"""
from __future__ import annotations
import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
from urllib.parse import parse_qs,urlsplit
from pathlib import Path
from zoneinfo import ZoneInfo
import re
import time

from tools.filing_review.network import PublicHTTP
from tools.ingest_alberta import parse_filings, page_url
from tools.manitoba_baseline import digest
from tools.review_disclosures import reconcile_listing, listing_identity

ROOT=Path(__file__).resolve().parents[1]
DOCUMENT_TYPES={'audited consolidated financial statements','schedule of remuneration and expenses'}


def now():
    return datetime.now(timezone.utc).isoformat()


def fiscal_years(end_year=None):
    # November 2026 -> years ended March 2022 through March 2026.
    today=datetime.now(ZoneInfo("America/Regina"))
    end_year=end_year or today.year-(today.month<4)
    return [f'{end-1}-{end}' for end in range(end_year-4,end_year+1)]


def valid_years(years):
    if not years or len(years)>30 or any(not isinstance(y,str) or not re.fullmatch(r'20\d{2}-20\d{2}',y) or int(y[-4:])!=int(y[:4])+1 for y in years):
        raise ValueError('Expected 1–30 fiscal-year pairs, such as 2023-2024')
    return list(dict.fromkeys(years))


def json_bytes(value):
    return (json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def atomic(path,raw):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.disclosure-scan.tmp')
    with temporary.open('wb') as handle:
        handle.write(raw);handle.flush();os.fsync(handle.fileno())
    os.replace(temporary,path)


def protected_digest(data):
    return digest([b for b in data['bands'] if b.get('province') in ('SK','AB')])


def scan_one(band,http,years,attempts=3,sleep=time.sleep):
    row=dict(bandId=str(band['id']),name=band['name'],province=band.get('province','Unknown'),
             bandNumber=band.get('iscBandNumber'),checkedAt=now(),attempts=[],sourceFilings=[])
    bid=band.get('iscBandNumber')
    if not isinstance(bid,int) or isinstance(bid,bool) or bid<1:
        return dict(row,status='identity_review_required',error='No verified ISC band number; profile IDs are never substituted.')
    if band.get('sharedIscIdentity'):
        return dict(row,status='shared_identity_review_required',error='Shared ISC identifier; filing ownership requires review for this separately administered profile.')
    row['sourceUrl']=page_url('FederalFundingMain',bid)
    for attempt in range(1,attempts+1):
        try:
            raw,final=http.get(row['sourceUrl'],limit=2_000_000)
            filings=[f for f in parse_filings(raw,bid) if f['year'] in years and f['docType'].casefold().strip() in DOCUMENT_TYPES]
            # Do not label a layout/parser failure as a successful empty listing.
            if not filings:
                from lxml import html
                links=html.fromstring(raw).xpath('//a[@href]')
                for link in links:
                    query={k.upper():v for k,v in parse_qs(urlsplit(link.get('href')).query).items()}
                    if query.get('FY',[''])[0] in years and query.get('DOC',[''])[0].casefold().strip() in DOCUMENT_TYPES:
                        raise ValueError('Financial document links were present but the listing table could not be parsed')
            row['attempts'].append(dict(at=now(),status='success'))
            return dict(row,status='checked',checkedAt=now(),sourceUrl=final,listingSha256=sha(raw),sourceFilings=filings)
        except Exception as error:
            row['attempts'].append(dict(at=now(),status='error',type=type(error).__name__,message=str(error)[:500]))
            transient=not isinstance(error,(PermissionError,ValueError)) and (isinstance(error,(TimeoutError,OSError)) or any(s in str(error) for s in ('HTTP 429','HTTP 500','HTTP 502','HTTP 503','HTTP 504')))
            delay=max(2**attempt,getattr(error,'retry_after',None) or 0)
            if not transient or attempt==attempts or delay>60:break
            sleep(delay)
    return dict(row,status='source_unavailable',error=row['attempts'][-1]['message'])


def reconcile_all(before,results,years):
    after=deepcopy(before);updates=[];anomalies=[]
    by_id={str(b['id']):b for b in after['bands']}
    for result in results:
        if result['status']!='checked':continue
        band=by_id[result['bandId']]
        # Prevalidate every source row on a copy: an invalid row cannot leave a
        # half-applied Nation when a later row fails validation.
        trial=deepcopy(band)
        changed=reconcile_listing(trial,result['sourceFilings'],set(years))
        for original in band.get('filings',[]):
            if original.get('year') not in years or original.get('docType','').casefold().strip() not in DOCUMENT_TYPES or not original.get('posted') or not original.get('href'):continue
            matches=[f for f in result['sourceFilings'] if f['year']==original['year'] and f['docType'].casefold().strip()==original.get('docType','').casefold().strip()]
            if not matches:
                anomalies.append(dict(bandId=result['bandId'],year=original['year'],documentType=original['docType'],reason='Indexed source absent from current listing; original record retained.'))
            elif not any(listing_identity(f['href'])==listing_identity(original['href']) for f in matches):
                anomalies.append(dict(bandId=result['bandId'],year=original['year'],documentType=original['docType'],reason='Different document URL; original source and values retained for review.'))
            elif any(f.get('date')!=original.get('date') for f in matches):
                anomalies.append(dict(bandId=result['bandId'],year=original['year'],documentType=original['docType'],reason='Posting date changed; original source and verified values retained for revision review.'))
        band.clear();band.update(trial)
        updates.extend(dict(bandId=result['bandId'],name=band['name'],year=f['year'],documentType=f['docType'],
            sourceUrl=result['sourceUrl'],pdfUrl=f['href'],postingDate=f['date'],previousAvailability=f.get('previousAvailability'),
            status='posted_pending_financial_verification') for f in changed)
    if updates:after['generated']=now()
    return after,updates,anomalies


def validate_transition(before,after,results,years):
    expected,_,_=reconcile_all(before,results,years)
    if after.get('generated')!=before.get('generated'):expected['generated']=after['generated']
    if after!=expected:raise ValueError('Refusing publication: changes exceed source-confirmed filing metadata')
    previous={str(b['id']):b for b in before['bands']}
    if set(previous)!={str(b['id']) for b in after['bands']}:raise ValueError('Nation roster changed')
    for band in after['bands']:
        old=previous[str(band['id'])]
        for filing in old.get('filings',[]):
            if filing.get('people') or (filing.get('posted') and filing.get('href')):
                if filing not in band.get('filings',[]):raise ValueError('Existing financial values or indexed sources changed')


def make_report(data,results,years,updates=(),anomalies=(),status='running'):
    counts=Counter(r['status'] for r in results)
    checked={r['bandId'] for r in results if r['status']=='checked'}
    missing=[]
    for band in data['bands']:
        for year in years:
            for kind in DOCUMENT_TYPES:
                if not any(f.get('year')==year and f.get('docType','').casefold().strip()==kind and f.get('posted') and f.get('href') for f in band.get('filings',[])):
                    missing.append(dict(bandId=str(band['id']),fiscalYear=year,documentType=kind,
                        status='not_indexed_after_listing_check' if str(band['id']) in checked else 'source_check_pending_or_blocked'))
    blocked=len(results)-counts['checked']
    return dict(schemaVersion=1,generated=now(),status=status,years=years,
        profilesExpected=len(data['bands']),profilesReviewed=len(results),profilesChecked=counts['checked'],
        sourceFailures=counts['source_unavailable'],identityReviews=counts['identity_review_required']+counts['shared_identity_review_required'],
        blockedProfiles=blocked,documentsRecovered=len(updates),nationsUpdated=len({u['bandId'] for u in updates}),
        missingDocumentSlots=len(missing),expectedAuditSlots=len(data['bands'])*len(years),expectedDocumentSlots=len(data['bands'])*len(years)*len(DOCUMENT_TYPES),
        notice='Not indexed or not publicly located does not mean an audit was not prepared or submitted. This scan checks ISC listings; broader source research remains separate.',
        results=results,updates=list(updates),retainedRecordWarnings=list(anomalies),missing=missing)


def recover_publication(state,allowed_paths=None):
    journal=Path(state)/'publication.json'
    if not journal.exists():return
    spec=json.loads(journal.read_text())
    if spec['status']=='complete':return
    if allowed_paths is not None and any(Path(item['path']).resolve() not in allowed_paths for item in spec['files']):
        raise ValueError('Publication journal belongs to a different dataset or destination')
    for item in spec['files']:
        if Path(item['staged']).name!=item['staged']:raise ValueError('Invalid publication checkpoint path')
        path=Path(item['path']);current=sha(path.read_bytes()) if path.exists() else None
        if current==item['after']:continue
        if current!=item['before']:raise ValueError('Interrupted publication conflicts with a newer file: '+str(path))
        content=(Path(state)/item['staged']).read_bytes()
        if sha(content)!=item['after']:raise ValueError('Publication checkpoint checksum changed')
        atomic(path,content)
    spec['status']='complete';atomic(journal,json_bytes(spec))


def publish(data_path,before_raw,after,results,years,updates,state,baseline_path=None,history_path=None):
    validate_transition(json.loads(before_raw),after,results,years)
    if not updates:return
    files=[(Path(data_path),json_bytes(after))]
    baseline_path=Path(baseline_path) if baseline_path else None
    if baseline_path:
        baseline=json.loads(baseline_path.read_text())
        old=protected_digest(json.loads(before_raw))
        if baseline['files']['data.json']!=old:
            raise ValueError('Preservation baseline differs before this scan; review existing changes before publishing metadata')
        baseline['files']['data.json']=protected_digest(after)
        files.append((baseline_path,json_bytes(baseline)))
    if history_path:
        history_path=Path(history_path)
        prior=history_path.read_bytes() if history_path.exists() else b''
        event=dict(at=now(),action='source_metadata_reconciled',dataBefore=sha(before_raw),dataAfter=sha(files[0][1]),
            protectedBefore=protected_digest(json.loads(before_raw)),protectedAfter=protected_digest(after),updates=updates)
        files.append((history_path,prior+(json.dumps(event,ensure_ascii=False,allow_nan=False)+'\n').encode()))
    # Optimistic guard against a different writer changing the input mid-scan.
    if Path(data_path).read_bytes()!=before_raw:raise ValueError('Dataset changed during scan; rerun against the new snapshot')
    spec=dict(status='pending',files=[])
    for i,(path,content) in enumerate(files):
        staged=f'publication-{i}.json';atomic(Path(state)/staged,content)
        spec['files'].append(dict(path=str(path.resolve()),before=sha(path.read_bytes()) if path.exists() else None,
                                 after=sha(content),staged=staged))
    atomic(Path(state)/'publication.json',json_bytes(spec))
    recover_publication(state,{p.resolve() for p,_ in files})


def run(data_path=ROOT/'data.json',report_path=ROOT/'disclosure-scan-report.json',state=ROOT/'.openband-ocr/disclosure-scan',
        years=None,write=False,resume=False,http=None,baseline_path=None,history_path=None):
    from tools.filing_review.pipeline import writer_lock
    state=Path(state);state.mkdir(parents=True,exist_ok=True)
    years=valid_years(years or fiscal_years())
    with writer_lock(state):
        if write:recover_publication(state,{Path(p).resolve() for p in (data_path,baseline_path,history_path) if p})
        raw=Path(data_path).read_bytes();data=json.loads(raw)
        if len({str(b['id']) for b in data['bands']})!=len(data['bands']):raise ValueError('Duplicate database profile IDs')
        identity=sha(json.dumps([years,[(str(b['id']),b.get('iscBandNumber'),b.get('name'),b.get('sharedIscIdentity')) for b in data['bands']]],sort_keys=True).encode())
        checkpoint=state/'checkpoint.json';saved=json.loads(checkpoint.read_text()) if resume and checkpoint.exists() else {}
        recent=False
        if saved.get('startedAt'):
            try:recent=datetime.now(timezone.utc)-datetime.fromisoformat(saved['startedAt'])<timedelta(hours=24)
            except ValueError:pass
        results=list(saved.get('results',[])) if recent and saved.get('identity')==identity else []
        results=[r for r in results if r['status'] in ('checked','identity_review_required','shared_identity_review_required')]
        completed={r['bandId'] for r in results};client=http or PublicHTTP()
        started=saved.get('startedAt') if results else now()
        for band in data['bands']:
            if str(band['id']) in completed:continue
            result=scan_one(band,client,years)
            results.append(result)
            atomic(checkpoint,json_bytes(dict(identity=identity,startedAt=started,results=results)))
            atomic(report_path,json_bytes(make_report(data,results,years)))
            print(f"[{len(results)}/{len(data['bands'])}] {band['name']}: {result['status']}",flush=True)
        after,updates,anomalies=reconcile_all(data,results,years)
        validate_transition(data,after,results,years)
        if write:publish(data_path,raw,after,results,years,updates,state,baseline_path,history_path)
        report=make_report(after if write else data,results,years,updates,anomalies,'complete_with_issues' if any(r['status']!='checked' for r in results) else 'complete')
        report['metadataApplied']=write;report['startedAt']=started
        atomic(report_path,json_bytes(report))
        return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data',type=Path,default=ROOT/'data.json')
    p.add_argument('--report',type=Path,default=ROOT/'disclosure-scan-report.json')
    p.add_argument('--state',type=Path,default=ROOT/'.openband-ocr/disclosure-scan')
    p.add_argument('--year',action='append',help='Fiscal year, repeatable; default is the latest five years ended March 31')
    p.add_argument('--write',action='store_true',help='Publish only safe source-listed availability metadata')
    p.add_argument('--resume',action='store_true',help='Resume successful source checks from the last 24 hours; retry failed sources')
    p.add_argument('--baseline',type=Path,help='Preservation guard: must match the input before updating only its data.json digest')
    p.add_argument('--history',type=Path,help='Append permanent availability-change history')
    args=p.parse_args()
    r=run(args.data,args.report,args.state,args.year,args.write,args.resume,baseline_path=args.baseline,history_path=args.history)
    print(json.dumps({k:v for k,v in r.items() if not isinstance(v,list)},indent=2))

if __name__=='__main__':main()
