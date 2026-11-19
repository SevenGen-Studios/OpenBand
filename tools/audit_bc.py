"""Audit BC source provenance, identities, empty financial scope and preservation."""
import json,hashlib,math
from collections import Counter
from datetime import date
from tools.bc_sources import *
from tools.merge_bc_enrichment import preserved,validate
from tools.bc_profile import current_officials
from tools.refresh_bc_roster import payload

def audit(root=ROOT,write=True):
 roster=read(root/'british-columbia-nations.json');nations=roster['nations'];data=read(root/'data.json');validate(nations,{'bands':[b for b in data['bands'] if b.get('province')!='BC']})
 issues=[];byid={str(b['id']):b for b in data['bands']};bc=[b for b in data['bands'] if b.get('province')=='BC'];ids={str(b['id']) for b in bc}
 if len(data['bands'])!=len(byid):issues.append('Duplicate application IDs')
 if ids!={str(b['id']) for b in nations}:issues.append('Roster/publication ID mismatch')
 phase3=(root/'bc-financial-index.json').exists()
 if not phase3 and any(b.get('filings')!=[] for b in bc):issues.append('BC financial arrays must remain empty in Phase 2')
 if not phase3 and any(k in read(root/'capital-data.json')['bands'] for k in ids):issues.append('BC financial summary found in Phase 2')
 baseline=read(CACHE/'protected-baseline.json');current=preserved(root)
 if phase3:
  import copy
  baseline=copy.deepcopy(baseline);current=copy.deepcopy(current)
  baseline['files'].pop('capital-data.json',None);current['files'].pop('capital-data.json',None)
  from tools.audit_bc_financials import audit as financial_audit
  try:financial_audit()
  except ValueError as error:issues.append(str(error))
 protected=current==baseline
 if not protected:issues.append('Existing province preservation mismatch')
 hashes={}
 for b in nations:
  published=byid.get(str(b['id']))
  if phase3 and published:published={**published,'filings':[],'financialIndexStatus':b['financialIndexStatus']}
  if published!=b:issues.append('Published BC profile differs from reviewed roster: '+str(b['id']))
  for s in b['sources']:
   if not s['url'].startswith(('https://','http://')):issues.append('Invalid source URL')
   if s.get('cacheFile') and s.get('sha256'):
    try:
     if s['cacheFile']not in hashes:hashes[s['cacheFile']]=hashlib.sha256(payload(s)).hexdigest()
     if hashes[s['cacheFile']]!=s['sha256']:issues.append('Source digest mismatch: '+s['cacheFile'])
    except FileNotFoundError:issues.append('Missing source evidence: '+s['cacheFile'])
  p=b.get('population')
  if p and (not p.get('sourcePeriod') or p.get('bandNumber')!=b.get('iscBandNumber')):issues.append('Population definition/identity/period missing')
  if b.get('treatyVerificationStatus')=='non_signatory':issues.append('BC non-signatory classifications are outside this reviewed dataset')
 maps=read(root/'map-data.json');locations={str(r['id']):r for r in maps['communities'] if str(r['id']) in ids};missing_ids={str(r['id']) for r in maps['missingLocations'] if str(r['id'])in ids}
 if set(locations)&missing_ids or set(locations)|missing_ids!=ids:issues.append('BC map coverage partition invalid')
 for r in locations.values():
  if not all(isinstance(r.get(k),(int,float)) and math.isfinite(r[k]) for k in ['latitude','longitude']):issues.append('Invalid coordinate')
 contacts=read(root/'contacts-data.json')['contacts'];logos=read(root/'first-nation-logos.json')['logos'];members=read(root/'member-counts.json')['bands']
 for rows,key,label in [(contacts,'nation_id','contacts'),(logos,'nation_id','logos')]:
  subset=[str(r[key]) for r in rows if str(r[key])in ids]
  if set(subset)!=ids or len(subset)!=len(ids):issues.append('Incomplete/duplicate BC '+label+' IDs')
 for k in members:
  if k in ids and not members[k].get('sourceYear'):issues.append('Population source year missing')
 boundary=read(CACHE/'boundary-validation.json');unresolved=[q for q in roster['manualReviewQueue'] if not q.get('resolution')]
 count=len(bc);coverage={'publishedProfiles':count,'uniqueVerifiedIscBandNumbers':sum(b.get('iscBandNumber')is not None for b in bc),'verifiedCommunityLocations':len(locations),'profilesWithReserveBoundaries':sum(bool(r.get('reserveLandIds')) for r in locations.values()),'verifiedReserveParcels':boundary['verifiedBCParcels'],'verifiedLogos':sum(bool(r.get('logo_verified')) for r in logos if str(r['nation_id'])in ids),'sourceListedOfficialWebsites':sum(bool(b.get('website')) for b in bc),'registeredPopulationProfiles':sum(bool(b.get('population')) for b in bc),'verifiedOfficePhones':sum(bool((b.get('contact')or{}).get('office_phone')) for b in bc),'verifiedMailingAddresses':sum(bool((b.get('contact')or{}).get('mailing_address')) for b in bc),'sourceDatedGovernanceProfiles':sum(bool(b.get('leadership')) for b in bc),'profilesWithTermCurrentOfficeholders':sum(bool(current_officials(b,date.today())) for b in bc)}
 report={'schemaVersion':1,'verifiedAt':roster['verifiedAt'],'asOfDate':date.today().isoformat(),'scope':roster['scope'],'denominators':{'iscIdentifiedBandVillageGovernments':roster['iscIdentityCount'],'publishedGovernmentAndAdministrationProfiles':count,'provincialListingRows':len(roster['reconciliation']),'provincialUniqueProfileUrls':len({r['url'] for r in roster['reconciliation']})},'coverage':coverage,'completionRates':{k:{'numerator':v,'denominator':count,'percent':round(100*v/count,1)} for k,v in coverage.items() if k not in ['verifiedReserveParcels','publishedProfiles']},'entityTypes':dict(Counter(b['entityType'] for b in bc)),'rosterReconciliationComplete':False,'auditPassed':not issues,'auditErrors':issues,'existingProvincialRecordsPreserved':protected,'reviewQueue':roster['manualReviewQueue'],'unresolvedReviewItems':unresolved,'missingFields':[{'id':b['id'],'name':b['name'],'missing':[k for k in ['population','leadership','website','location'] if not b.get(k)]+(['verifiedLogo'] if not b.get('logo_verified') else [])} for b in bc if any(not b.get(k) for k in ['population','leadership','website','location','logo_verified'])],'sourceAccessErrors':[e for p in CACHE.glob('*.error.json') for e in [read(p)] if not (e.get('url','').endswith('/robots.txt') and any(code in e.get('error','') for code in ['404','410']))]+[e for b in nations for e in b.get('sourceErrors',[])],'logoSearches':[{**entry,'logo_verified':str(entry['id']) in read(CACHE/'approved-logos.json'),'status':'verified' if str(entry['id']) in read(CACHE/'approved-logos.json') else entry['status']} for entry in read(CACHE/'logo-searches.json').values()] if (CACHE/'logo-searches.json').exists() else [],'financialScope':'No BC filings, PDFs, OCR, financial summaries, totals or remuneration were collected. Financial fields remain unindexed, not zero.','limitations':['The profile count spans overlapping band/village, national and community-administration levels; do not sum their populations.','Historical map and newer treaty evidence can disagree. Non-signatory status is never inferred from absent data.','Unresolved hereditary/governing-authority identities remain in the review queue; broad roster reconciliation is not claimed complete.','Three logos have visual/source/hash approval; remaining candidates use initials pending review.','Source-listed websites have provenance but are not a guarantee of current availability.']}
 if phase3:report['financialScope']='Phase 2 identity evidence remains unchanged. Phase 3 financial discovery, approved records and remaining extraction gaps are reported separately in bc-financial-coverage-report.json.'
 if write:
  atomic_write(root/'british-columbia-coverage-report.json',report)
  text='# British Columbia Phase 2 coverage\n\n'+report['scope']+'\n\n**Broad roster reconciliation remains open. This is not a claim of 100% completeness.**\n\n| Metric | Verified/indexed |\n|---|---:|\n'+''.join(f'| {k} | {v} |\n' for k,v in coverage.items())+'\nField coverage rates use '+str(count)+' published profiles. The ISC identity sub-roster has its own separately reported denominator.\n\n## Unresolved review items\n\n'+''.join('- '+str(q.get('name',q.get('id')))+': '+q['reason']+'\n' for q in unresolved)+'\n## Source conflicts\n\n'+''.join('- '+str(q.get('name',q.get('id')))+': '+q['reason']+' '+q.get('resolution','Awaiting review.')+'\n' for q in roster['manualReviewQueue'])+'\n## Preservation and boundaries\n\nAll pre-existing SK, AB and MB records and source geometry are preserved by the transaction baseline. '+str(boundary['verifiedBCParcels'])+' validated BC display parcels were added using the existing geometry validator. Parcel ownership and identifiers are retained; display geometry is not a legal survey.\n\n'+report['financialScope']+'\n\n## Limitations\n\n'+''.join('- '+x+'\n' for x in report['limitations'])+'\nSee the JSON report for every missing field, source-access error and percentage denominator.\n'
  (root/'british-columbia-coverage-report.md').write_text(text,encoding='utf-8')
 print(json.dumps({'coverage':coverage,'auditPassed':not issues,'errors':issues,'unresolved':len(unresolved)},ensure_ascii=True))
 return report
if __name__=='__main__':
 import sys
 if '--financial' in sys.argv:
  from tools.audit_bc_financials import audit as financial_audit
  print(financial_audit())
 else:raise SystemExit(not audit()['auditPassed'])
