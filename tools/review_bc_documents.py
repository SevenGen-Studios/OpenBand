"""Index an official-site PDF only after its entity, type and period are reviewed.

JSON manifest entries: bandId, url, listingUrl, documentTitle, docType,
fiscalYear, periodEnd, reportingEntity, reviewedAt, reviewer, evidence.
Shared statements require sharedFinancialScope=true and remain non-comparable.
No figures are accepted by this command.
"""
import argparse
from tools.ingest_bc import ROOT,INDEX,YEARS,read,roster,protect,atomic_write
from tools.bc_sources import now
def register(entries):
 protect();index=read(INDEX);governments=index['governments'];bands={str(b['id']):b for b in roster()}
 for entry in entries:
  bid=str(entry['bandId']);b=bands[bid];government=governments[bid]
  check=next((c for c in government['checks'] if c['url']==entry['listingUrl'] and c['status']=='checked'),None)
  if not check or entry['url'] not in {f['url'] for f in check.get('documentCandidates',[])}:raise ValueError('Document not found on checked official page')
  if entry['fiscalYear'] not in YEARS or entry['docType'] not in ('Audited consolidated financial statements','Schedule of Remuneration and Expenses'):raise ValueError('Reviewed period/type required')
  if entry['reportingEntity']!=b['officialName'] and not entry.get('sharedFinancialScope'):raise ValueError('Reporting entity differs; shared scope must be explicit')
  for field in ('periodEnd','reviewer','reviewedAt','evidence'):
   if not entry.get(field):raise ValueError('Missing '+field)
  if any(f['href']==entry['url'] for f in government['filings']):raise ValueError('Previously indexed document')
  government['filings'].append({'href':entry['url'],'year':entry['fiscalYear'],'docType':entry['docType'],'documentTitle':entry['documentTitle'],'reportingEntity':entry['reportingEntity'],'entityType':b['entityType'],'periodEnd':entry['periodEnd'],'posted':True,'people':[],'status':'available_pending_extraction','parse_status':'pending','sourceOrganization':'Official government website','sourceListingUrl':entry['listingUrl'],'sourceBandNumber':b.get('iscBandNumber'),'retrievedAt':now(),'officialSiteReview':entry,'sharedFinancialScope':bool(entry.get('sharedFinancialScope'))})
 atomic_write(INDEX,index)
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--manifest',required=True);register(read(p.parse_args().manifest))
