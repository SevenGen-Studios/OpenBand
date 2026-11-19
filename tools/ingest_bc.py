"""BC financial staging. Discovery and extraction never import public figures.

Use --discover, --parse --limit 20, --ocr --retry, --audit. Results and
hash-bound review batches live in .openband-ocr/british-columbia/.
"""
from __future__ import annotations
import argparse, hashlib, ipaddress, json, os, re, socket, sys, time, tempfile, subprocess
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from concurrent.futures import ThreadPoolExecutor, as_completed
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools import ingest_alberta as shared
from tools.bc_sources import atomic_write as _atomic_write, now
from lxml import html
CACHE=ROOT/'.openband-ocr/british-columbia'
INDEX=ROOT/'bc-financial-index.json'
REVISION='bc-financial-v4'
YEARS=[f'{y}-{y+1}' for y in range(2014,2026)]

def atomic_write(path,value):
 # OneDrive/virus scanning may briefly hold an existing checkpoint open.
 for attempt in range(12):
  try:return _atomic_write(path,value)
  except PermissionError:
   if attempt==11:raise
   time.sleep(.25*(attempt+1))

def read(path,default=None):
 return json.loads(Path(path).read_text(encoding='utf-8')) if Path(path).exists() else default
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def roster():return read(ROOT/'british-columbia-nations.json')['nations']
def safe_url(url,hosts):
 p=urlsplit(url)
 if p.scheme not in ('https','http') or p.username or p.password or p.port not in (None,80,443) or p.hostname not in hosts:raise ValueError('Unapproved official source host')
 if p.hostname in ('localhost',) or p.hostname.endswith('.local'):raise ValueError('Local source forbidden')
 for item in socket.getaddrinfo(p.hostname,None):
  if not ipaddress.ip_address(item[4][0]).is_global:raise ValueError('Nonpublic source address')
 return url
def download(url,refresh=False,hosts=None):
 url=shared.canonical_url(url)
 hosts=hosts or {urlsplit(url).hostname}
 safe_url(url,hosts);CACHE.mkdir(parents=True,exist_ok=True)
 key=hashlib.sha256(shared.canonical_url(url).encode()).hexdigest();path=CACHE/(key+'.source');meta=path.with_suffix('.json')
 if path.exists() and meta.exists() and not refresh:
  payload=path.read_bytes()
  if hashlib.sha256(payload).hexdigest()!=read(meta)['sha256']:raise ValueError('Cached source digest mismatch')
  return payload
 error=None
 class OfficialRedirects(HTTPRedirectHandler):
  def redirect_request(self,req,fp,code,msg,headers,newurl):
   safe_url(newurl,hosts)
   return super().redirect_request(req,fp,code,msg,headers,newurl)
 opener=build_opener(OfficialRedirects())
 for attempt in range(3):
  try:
   with opener.open(Request(url,headers={'User-Agent':'OpenBand/2.0 public financial source research (+https://openband.ca)'}),timeout=25) as response:
    safe_url(response.url,hosts);payload=response.read(45*1024*1024+1)
    if len(payload)>45*1024*1024:raise ValueError('Source exceeds 45 MiB')
   with tempfile.NamedTemporaryFile('wb',dir=CACHE,delete=False) as f:f.write(payload);f.flush();os.fsync(f.fileno());temp=f.name
   try:os.replace(temp,path)
   finally:
    if os.path.exists(temp):os.unlink(temp)
   atomic_write(meta,{'url':url,'sha256':hashlib.sha256(payload).hexdigest(),'retrievedAt':now(),'bytes':len(payload)})
   return payload
  except Exception as exc:error=exc;time.sleep(.4*(attempt+1))
 raise error
def baseline():
 data=read(ROOT/'data.json');ids={str(b['id']) for b in roster()}
 from tools.build_site import slugify
 tracked=set(subprocess.check_output(['git','ls-files','-z','--','first-nations'],cwd=ROOT).decode('utf-8').split('\0'))
 profiles=[p for b in data['bands'] if b.get('province')!='BC' for p in (ROOT/'first-nations'/slugify(b['name'])).rglob('*.html') if p.relative_to(ROOT).as_posix() in tracked]
 fixed=['map-data.json','public/reserve-boundaries.geojson','british-columbia-nations.json','member-counts.json','contacts-data.json','first-nation-logos.json','first-nation-logo-report.json','elections-data.json','history-data.json','community-enterprise.json']
 def file_digest(p):
  payload=p.read_bytes()
  if p.suffix in ('.html','.json','.geojson','.md','.txt'):payload=payload.replace(b'\r\n',b'\n')
  return hashlib.sha256(payload).hexdigest()
 return {'bands':digest([b for b in data['bands'] if b.get('province')!='BC']),
 'capital':digest({k:v for k,v in read(ROOT/'capital-data.json')['bands'].items() if k not in ids}),
 'files':{str(p.relative_to(ROOT)).replace('\\','/'):file_digest(p) for p in [*[ROOT/n for n in fixed],*sorted((ROOT/'manual_overrides').rglob('*')),*profiles] if p.is_file()}}
def protect():
 path=ROOT/'tools/bc-source-cache/financial-baseline.json';current=baseline()
 if path.exists():
  if read(path)!=current:raise ValueError('Protected provincial/profile baseline changed')
 else:atomic_write(path,current)
 for name,expected in read(CACHE/'local-protected-files.json',{}).items():
  p=ROOT/name
  if not p.exists() or hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest()!=expected:raise ValueError('Existing untracked local profile changed: '+name)
def discover_one(b,refresh=False):
 hosts={'services.sac-isc.gc.ca'};site=b.get('website');checks=[];docs=[]
 if site:hosts.add(urlsplit(site).hostname);hosts.add(('www.'+urlsplit(site).hostname) if not urlsplit(site).hostname.startswith('www.') else urlsplit(site).hostname[4:])
 if b.get('iscBandNumber'):
  url=shared.page_url('FederalFundingMain',b['iscBandNumber'])
  try:
   payload=download(url,refresh,hosts);docs=shared.parse_filings(payload,b['iscBandNumber']);checks.append({'url':url,'status':'checked','sha256':hashlib.sha256(payload).hexdigest(),'retrievedAt':now()})
  except Exception as e:checks.append({'url':url,'status':'source_unavailable','error':str(e),'retrievedAt':now()})
 if site:
  # Bounded official-site exploration. Unlabelled PDFs remain candidates, never
  # assigned a year or a reporting entity from their filename alone.
  pending=[site];seen=set()
  while pending and len(seen)<5:
   url=pending.pop(0)
   if url in seen:continue
   seen.add(url)
   try:
    payload=download(url,refresh,hosts);tree=html.fromstring(payload);candidates=[]
    for a in tree.xpath('//a[@href]'):
     target=urljoin(url,a.get('href'));label=' '.join(a.text_content().split());text=label+' '+target
     if urlsplit(target).hostname not in hosts:continue
     if re.search(r'financ|audit|remuneration|annual.report',text,re.I):
      if urlsplit(target).path.lower().endswith('.pdf'):candidates.append({'url':target,'label':label,'status':'manual_identity_period_review'})
      elif target not in seen and target not in pending:pending.append(target)
    pending.sort(key=lambda u:(bool(re.search(r'nvha|health|trust|fiscal.rel|capital.finance',u,re.I)),-int(bool(re.search(r'audited|financial.statement|remuneration|annual.report',u,re.I)))))
    checks.append({'url':url,'status':'checked','retrievedAt':now(),'sha256':hashlib.sha256(payload).hexdigest(),'documentCandidates':candidates})
   except Exception as e:checks.append({'url':url,'status':'source_unavailable','error':str(e),'retrievedAt':now()})
 for f in docs:
  f.update(reportingEntity=b['officialName'],entityType=b['entityType'],status='available_pending_extraction',periodEnd=None)
 return {'id':b['id'],'name':b['name'],'entityType':b['entityType'],'checks':checks,'filings':[f for f in docs if f['year'] in YEARS],
 'scope':'ISC listing and up to five linked official government pages; candidate PDFs require identity/period review. Missing listings do not establish noncompliance.'}
def configure():
 shared.CACHE=CACHE;shared.PARSER_REVISION=REVISION;shared.WORKER_SCRIPT=Path(__file__).resolve();shared.download=download;shared.write=atomic_write
 # No existing Alberta manual overrides apply to BC documents.
 shared.reviewed_remuneration=lambda *a:None
def merge_discovery(previous,row):
 """Failed or changed listings must not erase previously indexed sources."""
 for filing in previous.get('filings',[]):
  if any(f['href']==filing['href'] for f in row['filings']):continue
  if filing.get('officialSiteReview'):row['filings'].append(filing)
  else:row['filings'].append({**filing,'previouslyIndexed':True,'latestListingStatus':'source_unavailable' if any(c['status']=='source_unavailable' and 'FederalFundingMain' in c['url'] for c in row['checks']) else 'not_seen_in_latest_listing'})
 return row
def checkpoint_result(task,result):
 """A worker timeout must retain independently cached download evidence."""
 u=result[2];url=task[1]['href'];key=hashlib.sha256(shared.canonical_url(url).encode()).hexdigest();path=CACHE/(key+'.source');meta=read(path.with_suffix('.json'),{})
 if path.exists() and meta.get('sha256') and hashlib.sha256(path.read_bytes()).hexdigest()==meta['sha256'] and path.read_bytes()[:5]==b'%PDF-':
  u.setdefault('sha256',meta['sha256']);u.setdefault('byteSize',meta['bytes'])
 u.setdefault('status','manual_review_needed')
 if task[2] and any('TimeoutExpired' in w for w in u.get('warnings',[])):u['ocrStatus']='timeout'
 return result
def parse_task(task,refresh=False,retry=False):
 """Refresh source bytes before considering a worker-result cache reusable."""
 b,f,_=task;path=CACHE/(hashlib.sha256((str(b['id'])+f['href']).encode()).hexdigest()+'.result.json')
 try:
  payload=download(f['href'],refresh=True) if refresh else None
  previous=read(path)
  revised=bool(payload is not None and previous and previous[2].get('sha256')!=hashlib.sha256(payload).hexdigest())
  if path.exists() and (revised or retry and previous[2].get('status')!='validated'):path.unlink()
  return shared.bounded_parse(task)
 except Exception as error:return str(b['id']),f['href'],{'status':'source_unavailable','parse_status':'error','verificationStatus':'retrieval_or_parse_error','warnings':[f'{type(error).__name__}: {error}'],'lastChecked':now()},None
def financial_checks(summary,pages):
 warnings=[];refs=summary.get('sourceReferences',{});required=('totalRevenue','totalExpenses','annualSurplusDeficit')
 a,l,sur=(summary.get(k) for k in ('totalAssets','totalLiabilities','accumulatedSurplus'))
 if all(isinstance(v,(int,float)) for v in (a,l,sur)) and abs(a-l-sur)>max(2,abs(a)*.00001):warnings.append('Financial position requires manual reconciliation')
 if not all(refs.get(k,{}).get('pdfPage') for k in required):warnings.append('Required page provenance missing')
 if not all(refs.get(k,{}).get('yearValidated') is True for k in required):warnings.append('Actual current-year columns were not independently confirmed')
 if re.search(r'(?:amounts|expressed|stated|figures|dollars).{0,45}(?:in thousands|in millions)|in thousands of dollars|\$\s*[\x27\u2019]?000', '\n'.join(pages[:12]),re.I):warnings.append('Scaled currency units require independent multiplier review')
 return warnings
def conservative_revenue_fields(summary):
 """Shared heuristics are proposals, not BC accounting definitions."""
 labels=[str(r.get('originalLabel') or r.get('label') or '') for r in summary.get('sourceRevenueRows',[])]
 held=[]
 if not any(re.fullmatch(r'own.source revenue',label.strip(),re.I) for label in labels):
  if summary.get('ownSourceRevenue') is not None:held.append('ownSourceRevenue')
  summary['ownSourceRevenue']=None
 if any(re.search(r'gaming',label,re.I) for label in labels):
  if summary.get('businessRevenue') is not None:held.append('businessRevenue')
  summary['businessRevenue']=None
 if held:summary['bcWithheldClassifications']={'fields':held,'reason':'No explicit own-source aggregate or independently verified gaming business/transfer definition. Original revenue rows remain available with citations.'}
 return summary
def period_check(b,f,result):
 """Additional BC gates. Preserve raw evidence; never guess a March year-end."""
 _,_,u,s=result;warnings=[]
 if f.get('sharedFinancialScope'):warnings.append('Shared reporting entity requires independent allocation review; no automatic allocation')
 payload=download(f['href']);import io,pdfplumber
 with pdfplumber.open(io.BytesIO(payload)) as pdf:pages=[p.extract_text(layout=True) or '' for p in pdf.pages]
 atomic_write(CACHE/(hashlib.sha256(payload).hexdigest()+'.text.json'),{'sha256':hashlib.sha256(payload).hexdigest(),'pages':[{'pdfPage':i+1,'text':p} for i,p in enumerate(pages)]})
 cover='\n'.join(pages[:4]);ends=re.findall(r'(?:year|period)\s+ended\s+([A-Za-z]+\s+\d{1,2},?\s+20\d{2})',cover,re.I)
 from datetime import datetime
 parsed=[]
 for end in ends:
  try:parsed.append(datetime.strptime(end.replace(',',''),'%B %d %Y').date().isoformat())
  except ValueError:pass
 expected=int(f['year'].split('-')[1]);parsed=sorted(set(p for p in parsed if int(p[:4])==expected))
 if len(parsed)!=1:warnings.append('Exact reporting period end not confirmed from source cover')
 u['periodEnd']=parsed[0] if len(parsed)==1 else None;u['reportingEntity']=f.get('reportingEntity',b['officialName']);u['entityType']=b['entityType']
 if f.get('periodEnd') and f['periodEnd']!=u['periodEnd']:warnings.append('Reviewed source period conflicts with extracted cover date')
 if u.get('people'):
  # Shared heuristics can split names or infer generic titles. Preserve their
  # proposals for review, never certify original schedule distinctions from
  # arithmetic alone. Hash-bound visual reviews may restore exact rows.
  reviews=read(CACHE/'remuneration-reviews.json',{})
  review=reviews.get(hashlib.sha256(payload).hexdigest())
  if review and review.get('bandId')==str(b['id']) and review.get('fiscalYear')==f['year'] and review.get('footerReconciled') and review.get('reviewedAt') and review.get('pdfPage'):
   u.update(people=review['people'],sourceScheduleReview=review)
  else:
   u['proposedPeople']=u['people'];warnings.append('Exact source names, position titles, payment columns and schedule footer require review')
 if s:
  conservative_revenue_fields(s)
  s.update(periodEnd=u['periodEnd'],reportingEntity=b['officialName'],entityType=b['entityType'],comparisonEligible=False)
  warnings.extend(financial_checks(s,pages))
 if warnings:
  u.update(parse_status='manual_review',manual_review_required=True,people=[]);u.setdefault('warnings',[]).extend(warnings)
  if s:s.update(publishable=False,parseStatus='manual_review')
 valid=not warnings and bool(s and s.get('publishable') or u.get('people')) and u.get('documentChecks',{}).get('identityAndYearConfirmed',False)
 u['status']='validated' if valid else 'manual_review_needed'
 if s:
  # A fiscal label alone cannot establish entity/period comparability. A
  # reviewer must confirm currency, annual period and consolidated scope.
  s['comparisonEligible']=False
  s['comparisonReviewRequired']=True
 return result
def main():
 p=argparse.ArgumentParser(description=__doc__)
 for name in ('discover','parse','ocr','retry','refresh','audit'):p.add_argument('--'+name,action='store_true')
 p.add_argument('--band');p.add_argument('--year',choices=YEARS);p.add_argument('--document-type',choices=['all','audited','remuneration'],default='all');p.add_argument('--limit',type=int,default=20);p.add_argument('--workers',type=int,default=3);p.add_argument('--task');p.add_argument('--result')
 args=p.parse_args();configure()
 if args.task:
  task=read(args.task);result=shared.parse_one(task)
  try:result=period_check(task[0],task[1],result)
  except Exception as e:result[2].update(status='manual_review_needed',parse_status='manual_review',people=[],warnings=[str(e)]);result[3] and result[3].update(publishable=False)
  atomic_write(args.result,result);return
 protect();bands=[b for b in roster() if not args.band or str(b['id'])==args.band]
 index=read(INDEX,{'schemaVersion':1,'governments':{}})
 if args.discover:
  with ThreadPoolExecutor(max_workers=max(1,min(args.workers,4))) as pool:
   tasks={pool.submit(discover_one,b,args.refresh):b for b in bands if args.refresh or str(b['id']) not in index['governments']}
   for future in as_completed(tasks):
    b=tasks[future];bid=str(b['id']);row=future.result()
    row=merge_discovery(index['governments'].get(bid,{}),row)
    index['governments'][bid]=row;atomic_write(INDEX,index);print('Checked',b['id'],flush=True)
 if args.parse:
  queue=[];results=read(CACHE/'results.json',{})
  for b in bands:
   for f in index['governments'].get(str(b['id']),{}).get('filings',[]):
    key=digest([str(b['id']),f['href']]);old=results.get(key)
    if args.year and args.year!=f['year']:continue
    if args.document_type!='all' and (('remuneration' in f['docType'].lower())!=(args.document_type=='remuneration')):continue
    if old and old[2].get('parserRevision')==REVISION and not args.retry and not args.refresh:continue
    queue.append((b,f,args.ocr))
  queue.sort(key=lambda t:t[1]['year'],reverse=True)
  with ThreadPoolExecutor(max_workers=max(1,min(args.workers,4))) as pool:
   futures={pool.submit(parse_task,t,args.refresh,args.retry):t for t in queue[:max(0,args.limit)]}
   for future in as_completed(futures):
    t=futures[future];results[digest([str(t[0]['id']),t[1]['href']])]=checkpoint_result(t,future.result());atomic_write(CACHE/'results.json',results);print('Extracted',t[0]['id'],t[1]['year'],flush=True)
  batch={'parserRevision':REVISION,'results':results};batch['batchSha256']=digest(batch);atomic_write(CACHE/'review-batch.json',batch)
 from tools.bc_financial_report import report
 report();protect()
 if args.audit:
  from tools.audit_bc_financials import audit
  audit()
if __name__=='__main__':
 if '--task' in sys.argv:main()
 else:
  from tools.merge_bc_enrichment import writer_lock
  with writer_lock():main()
