"""Reuse the existing geometry-aware financial parser; never repair OCR numbers."""
from __future__ import annotations
from collections import defaultdict
from decimal import Decimal, InvalidOperation
import io
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
import unicodedata

IMPORTANT=('totalRevenue','totalExpenses','annualSurplusDeficit','totalAssets','totalLiabilities',
           'netFinancialAssetsDebt','accumulatedSurplus','governmentRevenue','cash')

def normalize_money(raw, scale=1):
    value=str(raw).strip().replace('−','-')
    if not re.fullmatch(r'\(?-?\$?\s*(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?\)?',value):
        raise ValueError('Ambiguous number; never substitute O/0, I/1, or punctuation')
    if value.startswith('(')!=value.endswith(')'): raise ValueError('Unbalanced negative parentheses')
    negative=value.startswith('(')
    if negative and '-' in value: raise ValueError('Ambiguous negative sign')
    try: amount=Decimal(value.strip('()').replace('$','').replace(',','').replace(' ',''))*Decimal(scale)
    except InvalidOperation as e: raise ValueError('Invalid amount') from e
    return str(-amount if negative else amount)

def compact(value):
    return re.sub(r'[^a-z0-9]','',unicodedata.normalize('NFKD',value).casefold())

def identify(slot,pages,url):
    from urllib.parse import parse_qs,urlsplit
    cover='\n'.join(p['text'] for p in pages[:3])
    text='\n'.join(p['text'] for p in pages)
    issues=[]
    names=[slot['name']]+slot.get('aliases',[])
    # Require a standalone report-heading identity, never a mention in a note.
    lines=[compact(s) for s in cover.splitlines() if s.strip()]
    name_ok=any(compact(name) in lines for name in names)
    if not name_ok: issues.append('document_identity_unconfirmed')
    if slot.get('identityUnconfirmed'): issues.append('band_identity_requires_review')
    q={k.lower():v for k,v in parse_qs(urlsplit(url).query).items()}
    if q.get('fy',[slot['fiscalYear']])[0]!=slot['fiscalYear']:issues.append('source_fiscal_year_mismatch')
    if q.get('band_number_ff',[str(slot['bandNumber'])])[0]!=str(slot['bandNumber']): issues.append('source_band_mismatch')
    end=slot['fiscalYear'][-4:]
    dates=re.findall(r'(?:year ended\s+|as at\s+|^\s*)(March|April|May|June|July|August|September|October|November|December|January|February)\s+(\d{1,2})(?:,\s*|\s+)(20\d{2})',pages[0]['text'] if pages else '',re.I|re.M)
    year_end=next((' '.join(d) for d in dates if d[2]==end),None)
    if not year_end: issues.append('fiscal_year_end_unconfirmed')
    auditor_pages=[p for p in pages if re.search(r"independent auditor[’']?s?[’']?\s+report",p['text'],re.I)]
    if not auditor_pages: issues.append('independent_auditor_report_missing')
    audited=bool(auditor_pages and re.search(r'financial statements|financial position',text,re.I))
    if not audited: issues.append('audited_financial_statements_unconfirmed')
    # A corporation on the title page cannot become the Nation's filing.
    entity_lines=[s for s in cover.splitlines()[:20] if re.search(r'corporation|\b(?:Ltd|Inc)\b|limited partnership',s,re.I)]
    title_entity=any(re.search(r'corporation|\b(?:Ltd|Inc)\b|limited partnership',line,re.I) for line in pages[0]['text'].splitlines()[:12]) if pages else False
    if (entity_lines and not name_ok) or title_entity: issues.append('possible_corporate_entity')
    audit_text='\n'.join(p['text'] for p in auditor_pages)
    opinion=None
    for label,pattern in [('disclaimer',r'disclaimer of opinion|do not express an opinion'),('adverse',r'adverse opinion'),('qualified',r'qualified opinion|except for the (?:effects|possible effects)'),('unmodified',r'in our opinion[\s\S]{0,700}present fairly')]:
        if re.search(pattern,audit_text,re.I): opinion=label;break
    if not opinion: issues.append('audit_opinion_unconfirmed')
    auditor=None
    m=re.search(r'^.*(?:MNP\s+LLP|Deloitte\s+LLP|KPMG\s+LLP|Grant Thornton\s+LLP|BDO Canada\s+LLP|PricewaterhouseCoopers\s+LLP).*$',audit_text,re.M|re.I)
    if m: auditor=m.group(0).strip()[:180]
    consolidated=bool(re.search(r'consolidated financial statements',cover,re.I))
    return dict(documentValid=not any(i in issues for i in ('document_identity_unconfirmed','source_band_mismatch','fiscal_year_end_unconfirmed','independent_auditor_report_missing','audited_financial_statements_unconfirmed','possible_corporate_entity','band_identity_requires_review','source_fiscal_year_mismatch')),
        issues=issues,yearEnd=year_end,auditor=auditor,opinion=opinion,
        documentType='consolidated' if consolidated else 'non-consolidated',auditorPages=[p['page'] for p in auditor_pages])

def ocr_page(page,number,engine):
    """Convert both independent engines' boxes into PDF points for the shared parser."""
    from tools.local_ocr import coordinate_lines
    image=page.to_image(resolution=300).original
    sx,sy=page.width/image.width,page.height/image.height
    items=[]
    if engine=='tesseract':
        import csv
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'page.png';image.save(path)
            result=subprocess.run(['tesseract',str(path),'stdout','--psm','6','tsv'],capture_output=True,text=True,check=True,timeout=120)
            for row in csv.DictReader(io.StringIO(result.stdout),delimiter='\t'):
                if not row['text'].strip():continue
                x,y,w,h=(float(row[k]) for k in ('left','top','width','height'))
                items.append(([[x,y],[x+w,y],[x+w,y+h],[x,y+h]],row['text']))
    else:
        from tools import local_ocr
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'page.png';image.save(path)
            local_ocr._rapidocr_text(path)  # Reuse the existing cached local model.
            result=local_ocr._RAPID_OCR(str(path))
            cells=result[0] if isinstance(result,tuple) else list(zip(result.boxes,result.txts))
            items=[(c[0],c[1]) for c in cells or []]
    words=[]
    for box,text in items:
        xs,ys=zip(*box)
        # Split OCR phrases only when they are words; multi-number boxes remain
        # ambiguous and the shared column parser will refuse those cells.
        words.append(dict(text=text,x0=min(xs)*sx,x1=max(xs)*sx,top=min(ys)*sy,bottom=max(ys)*sy))
    return dict(page=number,text=coordinate_lines(items),words=words)

def reconcile(records):
    """Return candidates for reconciliation, with presentation applicability explicit."""
    values={r['metric']:Decimal(str(r['value'])) for r in records if not r.get('dimension')}
    checks=[]
    rules=[('annual_result',('totalRevenue','totalExpenses','annualSurplusDeficit')),
           ('balance_sheet',('totalAssets','totalLiabilities','accumulatedSurplus')),
           ('net_financial_assets',('totalFinancialAssets','totalLiabilities','netFinancialAssetsDebt'))]
    for name,fields in rules:
        if all(f in values for f in fields):
            adjustment=sum((Decimal(str(r['value'])) for r in records if r['metric']=='surplusAdjustment'),Decimal(0)) if name=='annual_result' else Decimal(0)
            diff=values[fields[0]]-values[fields[1]]+adjustment-values[fields[2]]
            checks.append(dict(check=name,status='passed' if abs(diff)<=2 else 'review_presentation',difference=str(diff),
                explanation='Confirm presentation and separately recognized items before treating a difference as an error.'))
        else: checks.append(dict(check=name,status='not_applicable_or_missing_inputs'))
    return checks

def compare(primary,secondary):
    index=defaultdict(list)
    for r in secondary:index[(r['metric'],r.get('dimension',''))].append(r)
    for r in primary:
        matches=index[(r['metric'],r.get('dimension',''))]
        r['secondaryObservations']=matches
        same=len(matches)==1 and Decimal(str(matches[0]['value']))==Decimal(str(r['value'])) and matches[0].get('sourcePage')==r.get('sourcePage')
        r['verificationStatus']='independently_checked' if same and not r.get('validationFlags') and not matches[0].get('validationFlags') else 'manual_review'
        r['confidenceScore']=85 if r['verificationStatus']=='independently_checked' else 35
    return primary

def extract(raw,slot,url,sha):
    from tools.bandy_financial import read_pdf,extract_year,is_statement
    from tools.capital_parser import pdfplumber
    import importlib.util
    engines=[]
    if shutil.which('tesseract'):engines.append('tesseract')
    if importlib.util.find_spec('rapidocr_onnxruntime') or importlib.util.find_spec('rapidocr'):engines.append('rapidocr')
    document=dict(bandId=slot['bandId'],bandName=slot['name'],fiscalYear=slot['fiscalYear'],sourceUrl=url,sha256=sha)
    fixture=read_pdf(raw,document);pages=fixture['pages'];warnings=[];secondary=[]
    if len(pages)>300: raise ValueError('PDF exceeds 300-page processing limit')
    primary_method='native_pdf';scanned=[]
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        for n,p in enumerate(pages):
            if len(p['text'].strip())<80:
                scanned.append(n+1)
                if engines:
                    try: pages[n]=ocr_page(pdf.pages[n],n+1,engines[0]);primary_method='native_and_'+engines[0]
                    except Exception as e:warnings.append(f'page_{n+1}:primary_ocr_failed:{type(e).__name__}')
        verification_engine=engines[-1] if engines and (not scanned or len(engines)>1) else None
        for p in pages:
            if is_statement(p) and verification_engine:
                try:secondary.append(ocr_page(pdf.pages[p['page']-1],p['page'],verification_engine))
                except Exception as e:warnings.append(f"page_{p['page']}:secondary_ocr_failed:{type(e).__name__}")
    identity=identify(slot,pages,url)
    year=int(slot['fiscalYear'][-4:])
    records,issues=extract_year(document,pages,year) if pages else ([],['empty_pdf'])
    secondary_records=[]
    if secondary:
        # Identity comes from the complete PDF, while amounts use only OCR statement pages.
        secondary_records,_=extract_year(document,secondary,year)
        for r in secondary_records:r['extractionMethod']=verification_engine
    for r in records:
        r['extractionMethod']=primary_method;r['normalizedValue']=str(r['value'])
        r['rawOcrValue']=[v.get('rawValue') for v in r.get('sourceReferences',[])]
        r['statementTitle']=next((next((line for line in p['text'].splitlines()[:8] if 'statement' in line.lower()),p['text'].splitlines()[0]) for p in pages if p['page']==r.get('sourcePage')),None)
        r['sourcePdfSha256']=sha
    unlocated=[r for r in records if not r.get('sourcePage') or not r.get('sourceReferences') or any(ref.get('rawValue') is None for ref in r.get('sourceReferences',[]))]
    records=[r for r in records if r not in unlocated]
    records=compare(records,secondary_records)
    checks=reconcile(records)
    unresolved=sorted(set(identity['issues']+issues+warnings))
    if not verification_engine:unresolved.append('independent_ocr_unavailable')
    unresolved+=['figure_requires_review:'+r['recordId'] for r in records if r['verificationStatus']!='independently_checked']
    unresolved+=['reconciliation:'+c['check'] for c in checks if c['status']=='review_presentation']
    # Absence of a key figure must be explained by a reviewer, never filled with zero.
    unresolved+=['key_metric_not_extracted:'+m for m in IMPORTANT if not any(r['metric']==m and not r.get('dimension') for r in records)]
    identity['issues']=sorted(set(unresolved))
    extraction_failure=not records and identity['documentValid']
    return dict(**identity,records=records,unlocatedObservations=unlocated,secondaryRecords=secondary_records,checks=checks,
        extractionMethod=primary_method,secondaryEngine=verification_engine,
        confidenceScore=85 if records and not unresolved and identity['documentValid'] else 35 if records else 0,
        ocrFailure=bool((scanned and not engines) or warnings or extraction_failure),
        extractionStatus='failed_no_figures' if extraction_failure else 'partial_review_required' if unresolved else 'independently_checked',pages=pages,discoveredAt=__import__('tools.filing_review.store',fromlist=['now']).now(),sha256=sha)
