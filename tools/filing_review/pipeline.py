from __future__ import annotations
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import time
import subprocess
import sys
from urllib.parse import urljoin,urlsplit,urlencode,parse_qs
from urllib.request import Request,urlopen
from tools.filing_review.store import Store,ROOT,dump,key,now,read
from tools.filing_review.network import PublicHTTP,GOV_HOSTS

@contextmanager
def writer_lock(directory):
    # All service/CLI importers share this advisory lock; legacy ingestion must
    # be paused for production imports (documented in the deployment runbook).
    import fcntl
    with open(Path(directory)/'writer.lock','a') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX)
        try:yield
        finally:fcntl.flock(handle,fcntl.LOCK_UN)

class Pipeline:
    def __init__(self,store,root=ROOT,registry=None):
        self.store=store;self.root=Path(root)
        self.registry=registry or read(store.directory/'sources.json',{'sources':[]})
        hosts={urlsplit(s['url']).hostname for s in self.registry['sources'] if s.get('termsReviewed')}
        self.http=PublicHTTP(hosts)
        self.cache={}

    def fetch(self,url):
        if url not in self.cache:self.cache[url]=self.http.get(url)
        return self.cache[url]

    def queries(self,slot):
        names=[slot['name']]+slot.get('aliases',[])
        end=slot['fiscalYear'][-4:]
        return [f'"{name}" "{slot["bandNumber"] or ""}" {year} {kind}' for name in names[:4]
                for year,kind in [(slot['fiscalYear'],'audited financial statements'),(end,'consolidated financial statements'),(end,"independent auditor report annual financial report")]]

    def search_web(self,query):
        token=os.getenv('BRAVE_SEARCH_API_KEY')
        if not token:raise RuntimeError('Public web search provider is not configured')
        time.sleep(1)
        req=Request('https://api.search.brave.com/res/v1/web/search?'+urlencode({'q':query,'count':10}),
                    headers={'Accept':'application/json','X-Subscription-Token':token,'User-Agent':'OpenBandFilingReview/1.0'})
        with urlopen(req,timeout=30) as response:
            data=response.read(2_000_001)
            if len(data)>2_000_000:raise ValueError('Search response too large')
        return [r['url'] for r in json.loads(data).get('web',{}).get('results',[])]

    def discover(self,slotrow):
        from lxml import html
        slot=json.loads(slotrow['payload']);sid=slotrow['id'];failed=False;count=0
        sources=[]
        if slot.get('bandNumber'):
            sources.append('https://services.sac-isc.gc.ca/fnp/main/Search/FederalFundingMain.aspx?'+urlencode({'BAND_NUMBER':slot['bandNumber'],'lang':'eng'}))
        for source in self.registry['sources']:
            if source.get('termsReviewed') and str(source.get('bandId'))==slot['bandId']:sources.append(source['url'])
        found=[]
        def inspect(url,source,depth=0):
            nonlocal count,failed
            raw,final=self.fetch(url)
            if raw.lstrip().startswith(b'%PDF-'):
                self.store.candidate(sid,final,source);found.append(final);return
            tree=html.fromstring(raw)
            links=tree.xpath('//a[@href]')
            self.store.search(sid,url,'source_searched',f'{len(links)} links inspected')
            for link in links[:300]:
                target=urljoin(final,link.get('href')); label=link.text_content()+' '+target
                if urlsplit(target).hostname not in self.http.hosts:continue
                explicit_fy={k.lower():v for k,v in parse_qs(urlsplit(target).query).items()}.get('fy')
                year_match=(explicit_fy[0]==slot['fiscalYear']) if explicit_fy else slot['fiscalYear'] in label or slot['fiscalYear'][-4:] in label
                doc=bool(re.search(r'\.pdf(?:\?|$)|displaybinarydata',target,re.I))
                financial=bool(re.search(r'audit|financial|transparen|annual.report|consolidated|governance',label,re.I))
                if doc and financial and (year_match or not re.search(r'20\d{2}',label)):
                    self.store.candidate(sid,target,final);found.append(target)
                elif financial and not doc and depth<1 and count<10 and urlsplit(target).hostname==urlsplit(final).hostname and re.search(r'financial|audit|funding',label,re.I):
                    count+=1
                    try:inspect(target,final,depth+1)
                    except Exception as e:
                        failed=True;self.store.search(sid,target,'source_blocked',f'{type(e).__name__}: {e}')
        for url in sources:
            try:inspect(url,url)
            except Exception as e:
                failed=True;self.store.search(sid,url,'source_blocked',f'{type(e).__name__}: {e}')
        for query in self.queries(slot):
            try:
                urls=self.search_web(query)
                self.store.search(sid,'search:'+query,'search_results',dump(urls))
                for url in urls:
                    if urlsplit(url).hostname not in self.http.hosts:
                        self.store.search(sid,url,'host_review_required','Register source after reviewing ownership, terms and permissions');failed=True;continue
                    try:inspect(url,url)
                    except Exception as e:
                        failed=True;self.store.search(sid,url,'source_blocked',f'{type(e).__name__}: {e}')
            except Exception as e:
                failed=True;self.store.search(sid,'search:'+query,'search_unavailable',str(e));break
        # A bounded search with failures cannot support a negative availability conclusion.
        self.store.search(sid,'batch:discovery','search_incomplete' if failed else 'search_complete',f'{len(set(found))} candidate links; documents still require verification')
        return len(set(found))

    def process_one(self):
        db=self.store.db;stamp=time.time()
        db.execute('BEGIN IMMEDIATE')
        row=db.execute("SELECT c.* FROM candidates c JOIN slots s ON s.id=c.slot_id WHERE s.year IN (SELECT value FROM json_each(?)) AND ((c.state IN ('queued','failed') AND c.attempts<3 AND c.next_try<=?) OR (c.state='processing' AND c.lease<?)) ORDER BY c.attempts,json_extract(s.payload,'$.existingValid'),c.id LIMIT 1",(dump(self.store.active_years()),stamp,stamp)).fetchone()
        if not row:db.commit();return False
        row=dict(row)
        db.execute("UPDATE candidates SET state='processing',lease=?,attempts=attempts+1 WHERE id=?",(stamp+3600,row['id']));db.commit()
        slot=json.loads(db.execute('SELECT payload FROM slots WHERE id=?',(row['slot_id'],)).fetchone()[0])
        try:
            raw,final=self.http.get(row['url'])
            if not raw.lstrip().startswith(b'%PDF-'):raise ValueError('Response is not a PDF')
            sha=__import__('hashlib').sha256(raw).hexdigest()
            duplicate=db.execute("SELECT id,slot_id,payload FROM candidates WHERE sha256=? AND id<>? AND state NOT IN ('failed','processing') LIMIT 1",(sha,row['id'])).fetchone()
            path=self.store.pdfs/(sha+'.pdf')
            if not path.exists():path.write_bytes(raw)
            # Duplicate bytes are retained as a finding, but a document must still
            # pass identity/year verification for this slot (especially comparative years).
            if duplicate and duplicate['slot_id']==row['slot_id'] and json.loads(duplicate['payload']).get('documentValid'):
                result=json.loads(duplicate['payload'])
            else:
                worker=subprocess.run([sys.executable,'-m','tools.filing_review.worker'],
                    input=dump(dict(path=str(path),slot=slot,url=final,sha256=sha)),
                    capture_output=True,text=True,timeout=660,cwd=ROOT)
                if worker.returncode:raise RuntimeError('PDF/OCR worker failed: '+worker.stderr[-1500:])
                result=json.loads(worker.stdout)
            result.update(pdfUrl=final,sourceUrl=row['source'],originalRequestedUrl=row['url'])
            old=slot.get('existingSummary',{})
            differences=[]
            for r in result.get('records',[]):
                metric=r['metric']
                if not r.get('dimension') and old.get(metric) is not None and old[metric]!=r['value']:
                    differences.append(dict(metric=metric,previousValue=old[metric],proposedValue=r['value'],sourcePage=r.get('sourcePage'),sourceUrl=final))
                    result['issues'].append('existing_value_difference:'+metric)
            result['existingValueDifferences']=differences
            if duplicate:result['duplicateOf']=duplicate['id']
            self.store.save_candidate(row['id'],result,sha=sha)
        except Exception as e:
            attempt=row['attempts']+1
            payload=dict(error=type(e).__name__,message=str(e)[:1500],failedAt=now(),ocrFailure=False)
            self.store.save_candidate(row['id'],payload,'failed')
            db.execute('UPDATE candidates SET next_try=? WHERE id=?',(time.time()+min(3600,30*2**attempt),row['id']));db.commit()
        return True

    def run(self,kind='process',limit=25):
        jid=key(kind,now());self.store.db.execute('INSERT INTO jobs VALUES(?,?,?,?)',(jid,'running',dump({'kind':kind,'completed':0,'limit':limit}),now()));self.store.db.commit()
        completed=0
        try:
            if kind=='discover':
                for row in self.store.rows('slots'):
                    slot=json.loads(row['payload'])
                    if row['year'] not in self.store.active_years():continue
                    if slot['existingValid'] and not slot['gaps']:continue
                    if self.store.db.execute("SELECT 1 FROM searches WHERE slot_id=? AND status IN ('search_complete','search_incomplete')",(row['id'],)).fetchone():continue
                    self.discover(row);completed+=1
                    self.progress(jid,kind,completed,limit)
                    if completed>=limit:break
            else:
                while completed<limit and self.process_one():
                    completed+=1;self.progress(jid,kind,completed,limit)
            self.progress(jid,kind,completed,limit,'completed')
        except Exception as e:
            self.progress(jid,kind,completed,limit,'failed',str(e));raise
        return jid

    def progress(self,jid,kind,completed,limit,state='running',error=None):
        self.store.db.execute('UPDATE jobs SET state=?,payload=?,updated_at=? WHERE id=?',(state,dump(dict(kind=kind,completed=completed,limit=limit,error=error)),now(),jid));self.store.db.commit()

    def correct_figure(self,cid,metric,raw,scale,page,title,explanation,actor):
        from tools.filing_review.extraction import IMPORTANT,normalize_money
        row=self.store.db.execute('SELECT * FROM candidates WHERE id=?',(cid,)).fetchone()
        if not row or row['state']!='done':raise ValueError('Only completed, unapproved extractions can be edited')
        p=json.loads(row['payload'])
        if not p.get('documentValid'):raise ValueError('Verify document identity before correcting figures')
        if metric not in IMPORTANT or scale not in (1,1000,1000000):raise ValueError('Unsupported metric or unit scale')
        if not isinstance(page,int) or not 1<=page<=len(p.get('pages',[])):raise ValueError('PDF page required')
        if len(title.strip())<8 or len(explanation.strip())<12:raise ValueError('Statement title and source-based explanation required')
        number=normalize_money(raw,scale)
        previous=[r for r in p['records'] if r['metric']==metric and not r.get('dimension')]
        if len(previous)>1:raise ValueError('Conflicting duplicate metric requires document rejection or re-extraction')
        slot=json.loads(self.store.db.execute('SELECT payload FROM slots WHERE id=?',(row['slot_id'],)).fetchone()[0])
        record=dict(previous[0]) if previous else dict(recordId=key(cid,metric,'manual'),metric=metric,dimension='',comparative=False,
            fiscalYear=slot['fiscalYear'],sourceFiscalYear=slot['fiscalYear'],sourceDocument=p['pdfUrl'],sourceDocumentSha256=row['sha256'])
        record.update(value=float(number),normalizedValue=number,rawOcrValue=[raw],sourcePage=page,statementTitle=title,
            currency='CAD',unit='dollars',reportedScale=scale,extractionMethod='administrator_source_check',verificationStatus='manually_checked',
            confidenceScore=95,sourceReferences=[dict(pdfPage=page,rawValue=raw,selectedYear=int(slot['fiscalYear'][-4:]),selectedColumn='actual',
            statementTitle=title,scale=scale,explanation=explanation)],manualEvidence=explanation)
        p['records']=[r for r in p['records'] if r not in previous]+[record]
        from tools.filing_review.extraction import reconcile
        p['checks']=reconcile(p['records'])
        p['issues']=sorted(set(p.get('issues',[])+['manual_figure_change:'+metric]))
        self.store.db.execute('UPDATE candidates SET payload=? WHERE id=?',(dump(p),cid))
        self.store.event(cid,'figure_proposed',actor,previous,record,dict(page=page,explanation=explanation))
        self.store.db.commit()
        return record

    def review(self,cid,action,actor,evidence):
        row=self.store.db.execute('SELECT * FROM candidates WHERE id=?',(cid,)).fetchone()
        if not row:raise ValueError('Candidate not found')
        row=dict(row);p=json.loads(row['payload'])
        if row['state']=='imported':raise ValueError('Imported evidence is immutable; submit a new candidate revision')
        if action=='retry':
            if row['state'] in ('processing','approved'):raise ValueError('Candidate is busy or approved')
            self.store.db.execute("UPDATE candidates SET state='queued',attempts=0,next_try=0 WHERE id=?",(cid,))
        elif action=='reject':self.store.db.execute("UPDATE candidates SET state='rejected' WHERE id=?",(cid,))
        elif action=='approve':
            if row['state']!='done':raise ValueError('Only completed extractions can be approved')
            if not p.get('documentValid') or not p.get('records'):raise ValueError('Document identity/year/audit verification and extracted figures are required')
            if any(not r.get('sourcePage') or not r.get('sourceReferences') or any(ref.get('rawValue') is None for ref in r.get('sourceReferences',[])) for r in p['records']):raise ValueError('Every proposed financial figure requires its actual PDF page and raw source cell')
            if 'unsupported_currency' in p.get('issues',[]):raise ValueError('Unsupported currency must be resolved by a reviewed parser change, not automatic CAD normalization')
            resolutions=evidence.get('resolutions',{})
            for issue in p.get('issues',[]):
                r=resolutions.get(issue,{})
                if not isinstance(r,dict) or not isinstance(r.get('page'),int) or r['page']<1 or r['page']>len(p.get('pages',[])) or len(r.get('explanation','').strip())<12:
                    raise ValueError('Each unresolved issue requires a PDF page and a specific resolution: '+issue)
            if not evidence.get('confirmedSourceAndPresentation'):raise ValueError('Confirm original source, reporting entity, fiscal year, actual columns, units, and accounting presentation')
            p['resolutions']=resolutions;p['approvedAt']=now();p['approvedBy']=actor;p['confidenceScore']=95
            self.store.db.execute("UPDATE candidates SET state='approved',payload=? WHERE id=?",(dump(p),cid))
        else:raise ValueError('Unknown review action')
        self.store.event(cid,action,actor,row,{'state':action,'payload':p},evidence);self.store.db.commit()

    def import_approved(self,cid,actor,replace_existing=False):
        with writer_lock(self.store.directory):
            row=self.store.db.execute('SELECT * FROM candidates WHERE id=?',(cid,)).fetchone()
            if not row:raise ValueError('Candidate not found')
            if row['state']=='imported':return {'status':'already_imported'}
            if row['state']!='approved':raise ValueError('Administrator approval is required')
            p=json.loads(row['payload'])
            pdf=self.store.pdfs/(str(row['sha256'])+'.pdf')
            import hashlib
            if not p.get('documentValid') or not pdf.is_file() or hashlib.sha256(pdf.read_bytes()).hexdigest()!=row['sha256']:raise ValueError('Stored original PDF missing or checksum changed; reverify before import')
            slot=json.loads(self.store.db.execute('SELECT payload FROM slots WHERE id=?',(row['slot_id'],)).fetchone()[0])
            capital=read(self.root/'capital-data.json');data=read(self.root/'data.json')
            band=next(b for b in data['bands'] if str(b['id'])==slot['bandId'])
            years=capital['bands'].setdefault(slot['bandId'],{'name':slot['name'],'years':{}})['years']
            old=years.get(slot['fiscalYear'])
            values={r['metric']:r['value'] for r in p['records'] if not r.get('dimension') and not r.get('comparative')}
            proposal=dict(values,sourceUrl=p['pdfUrl'],sourceFiscalYear=slot['fiscalYear'],fiscalYear=slot['fiscalYear'],
                parseStatus='parsed',publishable=True,confidence='manual_reviewed',parser='filing_review_v1',
                verificationStatus='Verified',sha256=row['sha256'],sourceReferences={r['metric']:r.get('sourceReferences') for r in p['records'] if not r.get('dimension')},
                reviewCandidateId=cid,approvedBy=p['approvedBy'],approvedAt=p['approvedAt'],
                fieldVerification={r['metric']:{'status':'administrator_verified','sourceUrl':p['pdfUrl'],'sourcePage':r.get('sourcePage'),'candidateId':cid} for r in p['records'] if not r.get('dimension')})
            differing={k:{'previous':old.get(k),'proposed':v} for k,v in values.items() if old and old.get(k) is not None and old.get(k)!=v}
            if old and old.get('reviewCandidateId')!=cid and not replace_existing:
                self.store.event(cid,'replacement_proposed',actor,old,proposal,{'differences':differing,'requiresExplicitReplacementApproval':True});self.store.db.commit()
                return {'status':'replacement_requires_approval','differences':differing}
            # Preserve fields not covered by new evidence and permanent before images.
            merged=dict(old or {});merged.update(proposal);years[slot['fiscalYear']]=merged
            if not any(f.get('year')==slot['fiscalYear'] and f.get('sha256')==row['sha256'] for f in band['filings']):
                band['filings'].append(dict(year=slot['fiscalYear'],docType='Audited '+p['documentType']+' financial statements',href=p['pdfUrl'],sourceListingUrl=p['sourceUrl'],posted=True,sha256=row['sha256'],verificationStatus='Verified',reviewCandidateId=cid,people=[],parse_status='not_required'))
            self.store.event(cid,'import_prepared',actor,{'capital':old,'filings':next(b for b in read(self.root/'data.json')['bands'] if str(b['id'])==slot['bandId'])['filings']},proposal,{'replaceExisting':replace_existing,'differences':differing})
            self.store.db.commit()
            # Checkpoint both complete snapshots before atomic per-file replacements.
            # A crash between replacements is recoverable: rerun this idempotent import.
            for name,value in [('capital-data.json',capital),('data.json',data)]:
                original=(self.root/name).read_bytes()
                backup=self.store.directory/(key(cid,name,'before')+'.backup.json')
                if not backup.exists():backup.write_bytes(original)
                temporary=self.root/(name+'.filing-review.tmp')
                with open(temporary,'w') as f:
                    f.write(dump(value)+'\n');f.flush();os.fsync(f.fileno())
                os.replace(temporary,self.root/name)
            self.store.event(cid,'imported',actor,old,proposal,{'replaceExisting':replace_existing})
            self.store.db.execute("UPDATE candidates SET state='imported' WHERE id=?",(cid,));self.store.db.commit()
            return {'status':'imported'}
