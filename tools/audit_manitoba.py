"""Offline Manitoba coverage report; retrieval, availability and validation stay distinct."""
import hashlib
from collections import Counter,defaultdict
from datetime import datetime,timezone
from tools.ingest_manitoba import ROOT,SOURCE_CACHE,safe_write
from tools.ingest_alberta import read,now,canonical_url
from tools.manitoba_baseline import verify

def audit():
    registry=read(ROOT/'manitoba-nations.json',{'nations':[]})
    data=read(ROOT/'data.json');capital=read(ROOT/'capital-data.json')
    bands=[b for b in data['bands'] if b.get('province')=='MB']
    docs=[];nations=[];issues=[];hashes=defaultdict(list);urls=defaultdict(list)
    all_ids=[str(b['id']) for b in data['bands']]
    for bid,count in Counter(all_ids).items():
        if count>1:issues.append({'type':'duplicate_nation_id','nationId':bid,'severity':'error'})
    roster_ids={str(n['iscBandNumber']) for n in registry['nations']}
    if roster_ids!={str(b['id']) for b in bands}:issues.append({'type':'roster_integration_mismatch','severity':'error'})
    years=[f'{y}-{y+1}' for y in range(2014,datetime.now(timezone.utc).year)]
    for band in bands:
        fiscal={year:{} for year in years}
        for filing in band.get('filings',[]):
            if not filing.get('posted') or not filing.get('href'):continue
            doc={k:filing.get(k) for k in ('year','docType','sourceFormat','originalSourceFile','manualSourceReview','listedDocType','documentTypeMethod','href','sourceListingUrl','date','retrievedAt','lastChecked','sha256','parse_status','verificationStatus','documentChecks','warnings','ocrStatus','ocrAttemptHistory','requiresOcr','nativePageCount','nativeTextCharacters')}
            doc.update(nationId=band['id'],nation=band['name'])
            doc['retrieved']=bool(filing.get('sha256') and filing.get('httpStatus')==200)
            cached=ROOT/'.openband-ocr/manitoba'/hashlib.sha256(canonical_url(filing['href']).encode()).hexdigest()
            if not doc['retrieved'] and cached.exists():
                payload=cached.read_bytes()
                if payload.lstrip().startswith(b'%PDF-'):
                    doc.update(retrieved=True,sha256=hashlib.sha256(payload).hexdigest(),retrievalEvidence='Cached original PDF; extraction did not finish')
            doc['pdfRetrieved']=doc['retrieved'] and doc.get('sourceFormat')!='docx'
            summary=capital.get('bands',{}).get(str(band['id']),{}).get('years',{}).get(filing['year'],{})
            valid=bool(doc['retrieved'] and filing.get('verificationStatus')=='automated_validated' and filing.get('documentChecks',{}).get('identityAndYearConfirmed') and not filing.get('manual_review_required'))
            if 'audited' in filing['docType'].lower():valid=bool(valid and summary.get('publishable') and summary.get('parseStatus')=='parsed' and summary.get('sha256')==filing.get('sha256'))
            else:valid=bool(valid and filing.get('people'))
            if filing.get('verificationStatus')=='automated_validated' and not valid:issues.append({'type':'invalid_validated_marker','nationId':band['id'],'year':filing['year'],'url':filing['href'],'severity':'error'})
            doc['validated']=valid;docs.append(doc)
            listed_type=filing.get('listedDocType',filing['docType'])
            if listed_type!=filing['docType']:issues.append({'type':'listed_document_type_mismatch','nationId':band['id'],'year':filing['year'],'url':filing['href'],'listedDocType':listed_type,'actualDocType':filing['docType']})
            kind='audited' if 'audited' in listed_type.lower() else 'remuneration'
            fiscal.setdefault(filing['year'],{}).setdefault(kind,[]).append(doc)
            urls[canonical_url(filing['href'])].append(doc)
            if doc['sha256']:hashes[doc['sha256']].append(doc)
        for year,kinds in fiscal.items():
            for kind in ('audited','remuneration'):
                if kind not in kinds:kinds[kind]={'status':'not_posted' if band.get('discoveryStatus')=='checked' else 'listing_unchecked_or_failed'}
        incomplete=any(not d['validated'] for d in docs if d['nationId']==band['id']) or not band.get('filings')
        nations.append({'incompleteData':incomplete,'id':band['id'],'name':band['name'],'listingStatus':band.get('discoveryStatus','not_checked'),'sourceErrors':band.get('sourceErrors',[]),'fiscalYears':fiscal})
    for digest,rows in hashes.items():
        if len({(r['nationId'],r['year'],r['docType']) for r in rows})>1:issues.append({'type':'duplicate_document_hash','sha256':digest,'documents':rows})
    for url,rows in urls.items():
        if len(rows)>1:issues.append({'type':'duplicate_source_url','url':url})
    verify(read(SOURCE_CACHE/'protected-baseline.json'))
    counts={'expectedNations':63,'verifiedRosterNations':len(registry['nations']),'integratedNations':len(bands),'officialListingsChecked':sum(n['listingStatus']=='checked' for n in nations),'auditedPdfsDiscovered':sum('audited' in (d.get('listedDocType') or d['docType']).lower() for d in docs),'remunerationPdfsDiscovered':sum('remuneration' in (d.get('listedDocType') or d['docType']).lower() for d in docs),'pdfsRetrieved':sum(d['pdfRetrieved'] for d in docs),'sourceDocumentsRetrieved':sum(d['retrieved'] for d in docs),'validatedDocuments':sum(d['validated'] for d in docs),'pendingExtraction':sum(d['parse_status']=='pending' for d in docs),'reviewDocuments':sum(d['parse_status'] in ('manual_review','pending_manual_review') for d in docs),'technicalErrors':sum(d['parse_status']=='error' for d in docs),'sourceErrors':sum(len(n['sourceErrors']) for n in nations),'ocrAttempted':sum(bool((d.get('manualSourceReview') or {}).get('priorOcrAttempted')) or bool(d.get('ocrAttemptHistory')) or bool(d['ocrStatus']) and d['ocrStatus'] not in ('not_required_native_text','not_required_reviewed_source') for d in docs),'protectedProvinceChecksumsUnchanged':True}
    counts.update(validatedAuditedStatements=sum(d['validated'] and 'audited' in d['docType'].lower() for d in docs),validatedRemunerationSchedules=sum(d['validated'] and 'remuneration' in d['docType'].lower() for d in docs),nationsWithIncompleteData=sum(n['incompleteData'] for n in nations),documentsRequiringOcr=sum(bool(d['requiresOcr']) and not d['validated'] for d in docs),duplicateOrMismatchedDocuments=len(issues),missingFiscalYearDisclosures=sum(isinstance(value,dict) and value.get('status')=='not_posted' for n in nations for kinds in n['fiscalYears'].values() for value in kinds.values()))
    counts['ocrRequirementUnassessed']=sum(d['requiresOcr'] is None and not d['validated'] for d in docs)
    counts['boundedTimeouts']=sum('Bounded extraction stopped' in ' '.join(d.get('warnings') or []) for d in docs)
    counts['financialFieldReporting']={field:sum(s.get('publishable') is True and s.get('parseStatus')=='parsed' and isinstance(s.get(field),(int,float)) for b in bands for s in capital.get('bands',{}).get(str(b['id']),{}).get('years',{}).values()) for field in ('totalRevenue','totalExpenses','annualSurplusDeficit','totalAssets','totalLiabilities','accumulatedSurplus','cashInvestments','manitobaGovernmentRevenue')}
    result={'generated':now(),'summary':counts,'stages':{'rosterComplete':len(registry['nations'])==63,'discoveryComplete':counts['officialListingsChecked']==63,'nativeExtractionComplete':counts['pendingExtraction']==0,'recoveryAndReviewComplete':not counts['reviewDocuments'] and not counts['technicalErrors']},'issues':issues,'nations':nations,'documents':docs,'limitations':['Unposted is reported only after a successful official listing check.','Missing documents are not findings of noncompliance.','Unvalidated extractions are withheld; missing figures are not zero.','The current fiscal year may not yet be due or posted.','The OCR-required count flags known image-only documents; other unresolved tables may also need OCR or manual review.']}
    safe_write(ROOT/'manitoba-coverage-report.json',result)
    lines=['# Manitoba coverage audit','',f'Generated {result["generated"]}','']+[f'- {k}: {v}' for k,v in counts.items()]+['','| Nation | ISC band | Listing | Documents | Validated |','|---|---:|---|---:|---:|']
    for nation in nations:
        rows=[d for d in docs if d['nationId']==nation['id']]
        lines.append(f'| {nation["name"]} | {nation["id"]} | {nation["listingStatus"]} | {len(rows)} | {sum(d["validated"] for d in rows)} |')
    lines+=['','Fiscal-year document details, source errors and duplicate candidates are retained in `manitoba-coverage-report.json`.','']+result['limitations']
    (ROOT/'manitoba-coverage-report.md').write_text('\n'.join(lines)+'\n')
    print(counts,flush=True);return result
if __name__=='__main__':audit()
