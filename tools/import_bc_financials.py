"""Explicitly approved, hash-bound BC import; never called by refresh workflow."""
import argparse,copy,hashlib,os,tempfile
from tools.ingest_bc import ROOT,CACHE,INDEX,read,digest,protect,roster,download
from tools.bc_sources import atomic_write,now
from tools.merge_bc_enrichment import writer_lock
from tools import capital_parser

def approved_candidates(batch,approval):
 payload={k:v for k,v in batch.items() if k!='batchSha256'}
 if digest(payload)!=batch.get('batchSha256') or approval.get('batchSha256')!=batch.get('batchSha256'):raise ValueError('Approval batch digest mismatch')
 if approval.get('approved') is not True or not approval.get('reviewer') or not approval.get('approvedAt'):raise ValueError('Explicit dated reviewer approval required')
 keys=approval.get('candidateKeys',[])
 if not keys or len(keys)!=len(set(keys)):raise ValueError('Explicit unique candidate keys required')
 approved=[];seen=set()
 for key in keys:
  r=copy.deepcopy(batch['results'][key]);bid,url,u,s=r
  if u.get('status')!='validated' or not u.get('documentChecks',{}).get('identityAndYearConfirmed') or not u.get('periodEnd') or not u.get('sha256'):raise ValueError('Unvalidated candidate')
  if s and (not s.get('publishable') or not capital_parser.validate_summary(s).get('publishable')):raise ValueError('Accounting validation failed')
  comparison=approval.get('comparisonReviews',{}).get(key)
  if s and comparison:
   band=next((b for b in roster() if str(b['id'])==bid),{})
   if band.get('entityType')!='isc_band_or_village_government' or any(a.get('kind') in ('modern_treaty','self_government') for a in band.get('treatyAgreements',[])):raise ValueError('This reporting framework requires its own reviewed comparison policy')
   if comparison.get('basis')!='CAD-annual-March31-band-consolidated' or not comparison.get('sourceEvidence') or u['periodEnd'][-5:]!='03-31':raise ValueError('Unsupported comparison review')
   s.update(comparisonEligible=True,comparisonBasis=comparison['basis'],comparisonReviewRequired=False,comparisonReview=comparison)
  if not s and not u.get('people'):raise ValueError('No validated figures')
  if not s:
   from tools.parser_quality import validate_people
   if validate_people(u['people'],strict=True)['manual_review_required']:raise ValueError('Remuneration validation failed')
  if u['sha256'] in seen:raise ValueError('Duplicate/shared source requires separate entity review')
  seen.add(u['sha256']);approved.append((key,r))
 return approved

def transaction(values):
 backup=CACHE/'imports'/now().replace(':','-');backup.mkdir(parents=True)
 originals={name:(ROOT/name).read_bytes() for name in values};prepared={};written=[]
 try:
  for name,value in values.items():
   (backup/name).write_bytes(originals[name])
   with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=ROOT,delete=False) as f:
    import json
    json.dump(value,f,ensure_ascii=False,separators=(',',':') if name=='capital-data.json' else None,indent=None if name=='capital-data.json' else 2);f.write('\n');f.flush();os.fsync(f.fileno());prepared[name]=f.name
  for name,path in prepared.items():os.replace(path,ROOT/name);written.append(name)
  protect();atomic_write(backup/'transaction.json',{'state':'committed','files':written})
 except Exception:
  for name in reversed(written):
   with tempfile.NamedTemporaryFile('wb',dir=ROOT,delete=False) as f:f.write(originals[name]);path=f.name
   os.replace(path,ROOT/name)
  raise
 finally:
  for path in prepared.values():
   if os.path.exists(path):os.unlink(path)

def publish(approval_path,batch_path=None):
 approval=read(approval_path);batch=read(batch_path or CACHE/'review-batch.json');candidates=approved_candidates(batch,approval)
 with writer_lock():
  protect();data=read(ROOT/'data.json');capital=read(ROOT/'capital-data.json');index=read(INDEX)['governments'];bc={str(b['id']):b for b in data['bands'] if b.get('province')=='BC'};seen_years=set()
  existing_hashes={f.get('sha256') for b in data['bands'] for f in b.get('filings',[]) if f.get('sha256')}
  for key,(bid,url,u,s) in candidates:
   if bid not in bc:raise ValueError('Unknown BC identity')
   filing=next((f for f in index[bid]['filings'] if f['href']==url),None)
   if not filing or digest([bid,url])!=key:raise ValueError('Source not in reviewed BC discovery index')
   if hashlib.sha256(download(url)).hexdigest()!=u['sha256']:raise ValueError('Source digest changed')
   if u['sha256'] in existing_hashes:raise ValueError('Previously published identical/shared source requires replacement review')
   existing_hashes.add(u['sha256'])
   if s:
    yearkey=(bid,filing['year'])
    if yearkey in seen_years or filing['year'] in capital.get('bands',{}).get(bid,{}).get('years',{}):raise ValueError('Revised/duplicate statement requires explicit replacement review')
    seen_years.add(yearkey)
   f={**copy.deepcopy(filing),**u,'approval':{'batchSha256':batch['batchSha256'],'reviewer':approval['reviewer'],'approvedAt':approval['approvedAt']}}
   if any(old['href']==url for old in bc[bid]['filings']):raise ValueError('Previously published source; replacement review required')
   bc[bid]['filings'].append(f);bc[bid]['financialIndexStatus']='partially_indexed'
   if s:capital_parser.save_summary(capital,bc[bid],f,s)
  # Verify other province records in memory before touching public files.
  original=read(ROOT/'data.json');oldcapital=read(ROOT/'capital-data.json')
  if [b for b in original['bands'] if b.get('province')!='BC']!=[b for b in data['bands'] if b.get('province')!='BC']:raise ValueError('Protected province mutation')
  if {k:v for k,v in oldcapital['bands'].items() if k not in bc}!={k:v for k,v in capital['bands'].items() if k not in bc}:raise ValueError('Protected capital mutation')
  transaction({'data.json':data,'capital-data.json':capital})
  atomic_write(CACHE/'last-approved-import.json',approval)
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--approval',required=True);p.add_argument('--batch');args=p.parse_args();publish(args.approval,args.batch)
