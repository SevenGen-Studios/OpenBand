"""BC financial identity, source and publication audit, preserving Phase 2."""
from tools.ingest_bc import ROOT,INDEX,YEARS,read,roster,protect
from tools import capital_parser
def audit():
 protect();rows={str(b['id']):b for b in roster()};index=read(INDEX,{'governments':{}})['governments'];issues=[]
 for bid,b in index.items():
  if bid not in rows:issues.append('Unknown BC index identity '+bid);continue
  seen=set()
  for f in b['filings']:
   if f['year'] not in YEARS or f.get('sourceBandNumber')!=rows[bid].get('iscBandNumber'):issues.append('Filing year/identity mismatch '+bid)
   if f['href'] in seen:issues.append('Duplicate filing URL '+bid)
   seen.add(f['href'])
   if not f['href'].startswith('https://services.sac-isc.gc.ca/') and not f.get('officialSiteReview',{}).get('evidence'):issues.append('Unreviewed filing source '+bid)
 public=read(ROOT/'data.json');capital=read(ROOT/'capital-data.json')['bands']
 for b in public['bands']:
  if b.get('province')!='BC':continue
  original=rows[str(b['id'])];identity={k:v for k,v in b.items() if k not in ('filings','financialIndexStatus')};expected={k:v for k,v in original.items() if k not in ('filings','financialIndexStatus')}
  if identity!=expected:issues.append('Phase 2 identity changed '+str(b['id']))
  for f in b.get('filings',[]):
   if not f.get('approval',{}).get('batchSha256') or f.get('status')!='validated':issues.append('Unapproved public BC figures '+str(b['id']))
  for year,s in capital.get(str(b['id']),{}).get('years',{}).items():
   if not s.get('publishable') or not capital_parser.validate_summary(s).get('publishable'):issues.append('Unvalidated public summary '+str(b['id']))
   if not any(f.get('year')==year and f.get('sha256')==s.get('sha256') and f.get('approval') for f in b['filings']):issues.append('Summary lacks approved source '+str(b['id']))
 if issues:raise ValueError('; '.join(issues))
 return {'auditPassed':True,'governmentsChecked':len(index),'protectedProvincialRecordsPreserved':True}
if __name__=='__main__':print(audit())
