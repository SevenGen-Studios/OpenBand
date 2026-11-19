"""Coverage denominators distinguish discovery, extraction and approved publication."""
from collections import Counter
from tools.ingest_bc import ROOT,CACHE,INDEX,YEARS,read,roster,digest,atomic_write
from tools.bc_sources import now
def report():
 nations=roster();index=read(INDEX,{'governments':{}})['governments'];results=read(CACHE/'results.json',{});docs=[(str(b['id']),f) for b in index.values() for f in b['filings']]
 def selected(year=None):return [(bid,f) for bid,f in docs if year is None or f['year']==year]
 def counts(rows):
  extracted=[results[digest([bid,f['href']])] for bid,f in rows if digest([bid,f['href']]) in results]
  validated=[r for r in extracted if r[2].get('status')=='validated'];audited=lambda f:'remuneration' not in f['docType'].lower()
  return {'documentsDiscovered':len(rows),'auditedStatementsDiscovered':sum(audited(f) for _,f in rows),'remunerationSchedulesDiscovered':sum(not audited(f) for _,f in rows),'documentsProcessed':len(extracted),'documentsDownloaded':sum(bool(r[2].get('sha256')) for r in extracted),'documentsExtracted':sum(bool(r[2].get('nativeTextCharacters') or r[2].get('ocrStatus')=='ok_ocr_text') for r in extracted),'validatedCandidates':len(validated),'validatedAuditedStatements':sum(bool(r[3] and r[3].get('publishable')) for r in validated),'validatedRemunerationSchedules':sum(bool(r[2].get('people')) for r in validated),'manualReview':sum(r[2].get('status')!='validated' for r in extracted),'unprocessed':len(rows)-len(extracted),'ocrErrors':sum('error' in r[2].get('ocrStatus','') or r[2].get('ocrStatus')=='timeout' for r in extracted),'identityOrYearConflicts':sum(bool(r[2].get('documentChecks',{}).get('warnings')) for r in extracted),'fieldCoverage':dict(Counter(k for r in validated if r[3] for k,v in r[3].items() if isinstance(v,(int,float)) and not isinstance(v,bool)))}
 failures=[{'id':b['id'],**c} for b in index.values() for c in b['checks'] if c['status']=='source_unavailable']
 public=[b for b in read(ROOT/'data.json')['bands'] if b.get('province')=='BC'];published=[f for b in public for f in b['filings'] if f.get('approval')]
 published_urls={f['href'] for f in published};changed=False
 for bid,f in docs:
  result=results.get(digest([bid,f['href']]))
  if not result:continue
  u=result[2];status='validated' if f['href'] in published_urls else 'available_pending_approval' if u.get('status')=='validated' else 'manual_review_needed'
  updates={'status':status,'sourceDocumentSha256':u.get('sha256'),'periodEnd':u.get('periodEnd')}
  if any(f.get(k)!=v for k,v in updates.items()):f.update(updates);changed=True
 if changed:atomic_write(INDEX,{'schemaVersion':1,'governments':index})
 statuses=[]
 for b in nations:
  row=index.get(str(b['id']));checked=row and any(c['status']=='checked' and 'FederalFundingMain' in c['url'] for c in row['checks'])
  for year in YEARS:
   found=[f for f in (row or {}).get('filings',[]) if f['year']==year]
   if not row:status='not_assessed'
   elif found:status='validated' if all(f.get('status')=='validated' for f in found) else 'manual_review_needed' if any(f.get('status')=='manual_review_needed' for f in found) else 'available_pending_extraction'
   elif checked:status='not_found_in_checked_public_sources'
   elif any(c['status']=='source_unavailable' for c in row['checks']):status='source_unavailable'
   else:status='not_assessed'
   statuses.append({'id':b['id'],'year':year,'status':status,'filings':[{'url':f['href'],'docType':f['docType'],'status':f.get('status','available_pending_extraction')} for f in found],'scope':'Checked ISC listing only' if checked else 'Official website discovery; unassigned candidates do not establish a period','entityType':b['entityType'],'reportingFrameworkEvidence':[a for a in b.get('treatyAgreements',[]) if a.get('kind') in ('modern_treaty','self_government')]})
 pending=[{'id':bid,'year':f['year'],'docType':f['docType'],'url':f['href'],'status':results.get(digest([bid,f['href']]),[None,None,{}])[2].get('status','available_pending_extraction')} for bid,f in docs if results.get(digest([bid,f['href']]),[None,None,{}])[2].get('status')!='validated']
 out={'schemaVersion':1,'generatedAt':now(),'governmentsInVerifiedRoster':len(nations),'governmentsChecked':len(index),'governmentsWithDocuments':len({b for b,f in docs}),'officialWebsitePdfCandidates':sum(len(c.get('documentCandidates',[])) for b in index.values() for c in b['checks']),'totals':counts(docs),'byFiscalYear':{y:counts(selected(y)) for y in YEARS},'sourceRetrievalFailures':failures,'remainingQueue':pending,'checkpoint':'.openband-ocr/british-columbia/results.json','approvalBatch':'.openband-ocr/british-columbia/review-batch.json','publishedDocuments':0,'limitations':['Validated candidates require explicit batch approval before public import.','Official-site exploration is bounded to five relevant pages per government; PDF candidates require identity, period and type review.','Missing records in checked sources are not evidence of noncompliance.','Reporting frameworks are retained from verified identity sources; no legal applicability inferred from absence.','Full historical extraction is not claimed.'],'denominators':{'discoveryGovernments':len(nations),'extractionDocuments':len(docs)}}
 out['publishedDocuments']=len(published)
 out['governmentsWithValidatedAuditedStatements']=len({r[0] for r in results.values() if r[2].get('status')=='validated' and r[3]})
 out['governmentsWithValidatedRemunerationSchedules']=len({r[0] for r in results.values() if r[2].get('status')=='validated' and r[2].get('people')})
 out['publishedAuditedStatements']=sum('remuneration' not in f['docType'].lower() for f in published)
 out['publishedRemunerationSchedules']=sum('remuneration' in f['docType'].lower() for f in published)
 out['governmentYearDiscoveryStates']=statuses
 out['officialWebsitePdfCandidates']=len({f['url'] for b in index.values() for c in b['checks'] for f in c.get('documentCandidates',[])})
 out['documentRetrievalOrParseErrors']=[{'id':r[0],'url':r[1],'warnings':r[2].get('warnings',[])} for r in results.values() if r[2].get('verificationStatus')=='retrieval_or_parse_error']
 out['ocr']={'attempted':sum(bool(r[2].get('ocrRequested') or r[2].get('ocrStatus')=='timeout') for r in results.values()),'textRecovered':sum(r[2].get('ocrStatus')=='ok_ocr_text' for r in results.values()),'boundedTimeouts':sum(r[2].get('ocrStatus')=='timeout' for r in results.values()),'publishedFromOcr':sum(bool(f.get('ocrRequested')) for f in published)}
 capital=read(ROOT/'capital-data.json')['bands']
 out['comparisonReviewRequired']=[{'id':b['id'],'year':year,'reason':'Currency, annual-period and consolidated entity comparability require explicit source review'} for b in public for year,s in capital.get(str(b['id']),{}).get('years',{}).items() if not s.get('comparisonEligible')]
 out['totals']['ocrErrors']=out['ocr']['boundedTimeouts']+sum('error' in r[2].get('ocrStatus','') for r in results.values())
 def rate(n,d):return {'numerator':n,'denominator':d,'percent':round(n*100/d,2) if d else None}
 out['rates']={'governmentsChecked':rate(len(index),len(nations)),'governmentsWithDiscoveredDocuments':rate(out['governmentsWithDocuments'],len(nations)),'documentsProcessed':rate(out['totals']['documentsProcessed'],len(docs)),'validatedOfDiscovered':rate(out['totals']['validatedCandidates'],len(docs)),'validatedOfProcessed':rate(out['totals']['validatedCandidates'],out['totals']['documentsProcessed'])}
 fields=('totalRevenue','totalExpenses','annualSurplusDeficit','totalAssets','totalLiabilities','accumulatedSurplus','cash','investments','capitalAssets','netFinancialAssetsDebt','iscRevenue','federalGovernmentRevenue','governmentRevenue','ownSourceRevenue','businessRevenue')
 validated_audits=[r[3] for r in results.values() if r[2].get('status')=='validated' and r[3]]
 out['verifiedFinancialFieldCoverage']={key:rate(sum(s.get(key) is not None for s in validated_audits),len(validated_audits)) for key in fields}
 for year,c in out['byFiscalYear'].items():c['processingRate']=rate(c['documentsProcessed'],c['documentsDiscovered']);c['validationRate']=rate(c['validatedCandidates'],c['documentsDiscovered'])
 atomic_write(ROOT/'bc-financial-coverage-report.json',out)
 lines=['# British Columbia financial coverage','',f"Governments checked: {len(index)} / {len(nations)}. Governments with indexed documents: {out['governmentsWithDocuments']}.",'','Validation counts describe staged candidates. Public financial import requires explicit approval.','','| Fiscal year | Audits found | Remuneration found | Processed | Validated candidates | Remaining |','|---|---:|---:|---:|---:|---:|']
 for y,c in out['byFiscalYear'].items():lines.append(f"| {y} | {c['auditedStatementsDiscovered']} | {c['remunerationSchedulesDiscovered']} | {c['documentsProcessed']} | {c['validatedCandidates']} | {c['unprocessed']} |")
 lines+=['',f"Published after explicit approval: {out['publishedAuditedStatements']} audited statements and {out['publishedRemunerationSchedules']} remuneration schedules.",'',f"Source retrieval failures: {len(failures)}. Unique official-site PDF candidates requiring identity/period review: {out['officialWebsitePdfCandidates']}.",'','Discovery denominator: 204 verified profiles (overlapping government levels). Extraction denominator: indexed documents, separately from governments. No publication rate is a compliance assessment.','','## Limitations','']+['- '+s for s in out['limitations']]
 (ROOT/'bc-financial-coverage-report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8');return out
if __name__=='__main__':report()
