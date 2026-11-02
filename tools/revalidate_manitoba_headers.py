"""Revalidate cached native statements after the source-year header correction.

Reuses the shared identity and financial parsers. Never relaxes reconciliation
or replaces an existing publishable statement with an alternate source.
"""
import argparse
import hashlib
import json
from pathlib import Path
import pypdfium2
from tools import ingest_alberta as engine
from tools.capital_parser import parse_page_texts,save_summary
from tools.ingest_manitoba import configure,dataset_lock,safe_write,ROOT

def recover(limit=0,timeouts_only=False):
    configure();result={'generated':engine.now(),'attempted':0,'recovered':0,'records':[]}
    with dataset_lock():
        data=engine.read(ROOT/'data.json');capital=engine.read(ROOT/'capital-data.json')
        selected=[(b,f) for b in data['bands'] if b.get('province')=='MB' for f in b.get('filings',[]) if 'audited' in f['docType'].lower() and f.get('verificationStatus')!='automated_validated' and (f.get('verificationStatus')=='parse_timeout_or_error' if timeouts_only else any('wrong fiscal-year column' in w for w in f.get('warnings',[])))]
        if limit:selected=selected[:limit]
        for band,filing in selected:
            row={'nationId':band['id'],'year':filing['year'],'url':filing['href'],'recovered':False}
            result['attempted']+=1
            try:
                source=engine.CACHE/hashlib.sha256(engine.canonical_url(filing['href']).encode()).hexdigest()
                payload=source.read_bytes();digest=hashlib.sha256(payload).hexdigest()
                if digest!=filing.get('sha256'):raise ValueError('Cached source digest differs from the indexed document')
                pages=[]
                with pypdfium2.PdfDocument(payload) as pdf:
                    for page in pdf:
                        text=page.get_textpage()
                        try:pages.append(text.get_text_range().replace('\r',''))
                        finally:text.close();page.close()
                issues=engine.document_identity(pages,band,filing)
                actual_type=engine.document_type_from_cover(pages)
                if actual_type and 'audited' not in actual_type.lower():issues.append('Cover document type differs from an audited statement')
                summary=parse_page_texts(pages,filing['href'],filing['year'],require_reported_totals=True)
                existing=capital.get('bands',{}).get(str(band['id']),{}).get('years',{}).get(filing['year'],{})
                if existing.get('publishable') and existing.get('sha256')!=digest:issues.append('Existing validated alternate statement preserved')
                row['warnings']=list(dict.fromkeys(issues+summary.get('warnings',[])))
                filing['lastNativeHeaderRevalidation']={'checkedAt':engine.now(),'parserRevision':engine.PARSER_REVISION,'warnings':row['warnings']}
                if not issues and summary.get('publishable') and summary.get('parseStatus')=='parsed':
                    summary.update(sha256=digest,requiresReportedTotals=True)
                    save_summary(capital,band,filing,summary)
                    if summary.get('publishable'):
                        filing.update(parse_status='parsed',parse_confidence=summary.get('confidence','medium'),manual_review_required=False,verificationStatus='automated_validated',documentChecks={'identityAndYearConfirmed':True,'method':'Original cover rechecked independently of year-column normalization'},parserRevision=engine.PARSER_REVISION,extractionMethod='Native PDF text; printed spaced-year header normalized only for column validation; reported totals reconciled',warnings=summary.get('warnings',[]),lastChecked=engine.now(),people=[])
                        row['recovered']=True;result['recovered']+=1
            except Exception as error:row['error']=f'{type(error).__name__}: {error}'
            result['records'].append(row)
            if result['attempted']%10==0:
                safe_write(ROOT/'data.json',data);safe_write(ROOT/'capital-data.json',capital)
            print(f"{result['attempted']}/{len(selected)} {band['id']} {filing['year']}: {'validated' if row['recovered'] else 'withheld'}",flush=True)
        safe_write(ROOT/'data.json',data);safe_write(ROOT/'capital-data.json',capital)
    safe_write(ROOT/('manitoba-timeout-native-recovery-report.json' if timeouts_only else 'manitoba-header-recovery-report.json'),result)
    print('Recovered',result['recovered'],'of',result['attempted'],flush=True)
    return result
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--limit',type=int,default=0);p.add_argument('--timeouts-only',action='store_true');args=p.parse_args();recover(args.limit,args.timeouts_only)
