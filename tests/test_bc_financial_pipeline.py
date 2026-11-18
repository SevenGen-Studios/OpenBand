import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from tools import ingest_bc as bc
from tools.import_bc_financials import approved_candidates

class BCFinancialPipelineTests(unittest.TestCase):
 def test_roster_is_verified_and_unique(self):
  rows=bc.roster();self.assertEqual(len(rows),204);self.assertEqual(len({str(b['id']) for b in rows}),204)
  self.assertTrue(all(b.get('verifiedAt') and b.get('sources') for b in rows))
 def test_year_range_includes_recent_completed_year(self):
  self.assertEqual(bc.YEARS[0],'2014-2015');self.assertEqual(bc.YEARS[-1],'2025-2026');self.assertEqual(len(bc.YEARS),12)
 def test_wrong_isc_identity_and_year_rejected(self):
  with self.assertRaises(ValueError):bc.shared.parse_filings(b'<main>Number 605</main>',604)
  payload=b'<main>Number 604</main>'
  self.assertEqual(bc.shared.parse_filings(payload,604),[])
 def test_url_validation_rejects_nonofficial_or_private_sources(self):
  for url in ['file:///tmp/test.pdf','https://bad.example/x','http://localhost/x','https://user:pass@official.example/x']:
   with self.subTest(url=url),self.assertRaises(ValueError):bc.safe_url(url,{'official.example','localhost'})
  with patch.object(bc.socket,'getaddrinfo',return_value=[(None,None,None,None,('127.0.0.1',0))]):
   with self.assertRaises(ValueError):bc.safe_url('https://official.example/x',{'official.example'})
 def test_cache_hash_is_verified(self):
  with tempfile.TemporaryDirectory() as d,patch.object(bc,'CACHE',Path(d)),patch.object(bc,'safe_url'):
   url='https://official.example/x';key=__import__('hashlib').sha256(bc.shared.canonical_url(url).encode()).hexdigest();p=Path(d)/(key+'.source');p.write_bytes(b'changed');bc.atomic_write(p.with_suffix('.json'),{'sha256':'wrong'})
   with self.assertRaises(ValueError):bc.download(url)
 def test_approval_is_explicit_hash_bound_and_nonempty(self):
  batch={'parserRevision':'test','results':{}};batch['batchSha256']=bc.digest(batch)
  with self.assertRaises(ValueError):approved_candidates(batch,{'approved':True,'batchSha256':'wrong'})
  with self.assertRaises(ValueError):approved_candidates(batch,{'approved':True,'batchSha256':batch['batchSha256'],'reviewer':'reviewer','approvedAt':'2026-11-18','candidateKeys':[]})
 def test_manual_review_and_wrong_identity_cannot_import(self):
  for update in [{'status':'manual_review_needed'},{'status':'validated','periodEnd':'2026-03-31','sha256':'abc','documentChecks':{'identityAndYearConfirmed':False}}]:
   batch={'results':{'k':['604','https://official.example/x',update,None]}};batch['batchSha256']=bc.digest(batch)
   with self.assertRaises(ValueError):approved_candidates(batch,{'approved':True,'batchSha256':batch['batchSha256'],'reviewer':'reviewer','approvedAt':'2026-11-18','candidateKeys':['k']})
 def test_shared_document_cannot_be_allocated_twice(self):
  u={'status':'validated','periodEnd':'2026-03-31','sha256':'abc','documentChecks':{'identityAndYearConfirmed':True},'people':[{'name':'Public disclosure'}]}
  batch={'results':{'a':['604','a',u,None],'b':['605','b',u,None]}};batch['batchSha256']=bc.digest(batch)
  with self.assertRaises(ValueError):approved_candidates(batch,{'approved':True,'batchSha256':batch['batchSha256'],'reviewer':'reviewer','approvedAt':'2026-11-18','candidateKeys':['a','b']})
 def test_protected_baseline_matches(self):bc.protect()
 def test_workflow_has_no_import_or_push(self):
  text=(bc.ROOT/'.github/workflows/bc-financial-ingestion.yml').read_text();self.assertNotIn('import_bc_financials',text);self.assertNotIn('git push',text);self.assertIn('contents: read',text)
 def test_current_year_pages_and_financial_position(self):
  s={'totalAssets':100,'totalLiabilities':30,'accumulatedSurplus':70,'sourceReferences':{k:{'pdfPage':4,'yearValidated':True} for k in ('totalRevenue','totalExpenses','annualSurplusDeficit')}}
  self.assertEqual(bc.financial_checks(s,['Annual statement']),[])
  s['totalAssets']=101;self.assertEqual(bc.financial_checks(s,['Annual statement']),[]) # rounding tolerance
  s['totalAssets']=110;self.assertTrue(bc.financial_checks(s,['Annual statement']))
  s['totalAssets']=100;s['sourceReferences']['totalRevenue']['yearValidated']=False
  self.assertTrue(any('current-year' in w for w in bc.financial_checks(s,['Annual statement'])))
 def test_scaled_units_and_missing_provenance_withheld(self):
  warnings=bc.financial_checks({},['Amounts expressed in thousands of dollars'])
  self.assertTrue(any('multiplier' in w for w in warnings));self.assertTrue(any('provenance' in w for w in warnings))
 def test_timeout_keeps_manual_review_and_ocr_error(self):
  with tempfile.TemporaryDirectory() as directory,patch.object(bc,'CACHE',Path(directory)):
   result=['604','https://official.example/source',{'warnings':['Bounded extraction stopped: TimeoutExpired']},None]
   result=bc.checkpoint_result(({'id':604},{'href':result[1]},True),result)
   self.assertEqual(result[2]['status'],'manual_review_needed');self.assertEqual(result[2]['ocrStatus'],'timeout')
 def test_profile_has_sources_and_does_not_infer_missing_zero(self):
  from tools.bc_financial_profile import financial_sources_markup
  b=next(b for b in bc.roster() if b['id']==604);text=financial_sources_markup(b)
  self.assertIn('Available documents',text);self.assertIn('pending extraction and approval',text);self.assertIn('Missing values are not zero',text)
 def test_gaming_transfers_are_not_assumed_own_source_business(self):
  s={'sourceRevenueRows':[{'originalLabel':'BC Gaming revenue','amount':100}],'ownSourceRevenue':100,'businessRevenue':100}
  bc.conservative_revenue_fields(s);self.assertIsNone(s['ownSourceRevenue']);self.assertIsNone(s['businessRevenue']);self.assertEqual(s['sourceRevenueRows'][0]['amount'],100)
 def test_same_url_revised_pdf_invalidates_worker_cache(self):
  with tempfile.TemporaryDirectory() as d,patch.object(bc,'CACHE',Path(d)),patch.object(bc,'download',return_value=b'%PDF-revised') as fetch:
   task=({'id':604},{'href':'https://official.example/a.pdf'},False);key=bc.hashlib.sha256(('604'+task[1]['href']).encode()).hexdigest();p=Path(d)/(key+'.result.json');bc.atomic_write(p,['604',task[1]['href'],{'sha256':'old','status':'validated'},None])
   with patch.object(bc.shared,'bounded_parse',side_effect=lambda _:self.assertFalse(p.exists())):self.assertIsNone(bc.parse_task(task,refresh=True))
   fetch.assert_called_once_with(task[1]['href'],refresh=True)
 def test_unavailable_refresh_retains_previous_source_links(self):
  old={'filings':[{'href':'https://official.example/a.pdf','year':'2025-2026'}]};new={'filings':[],'checks':[{'url':'https://services.sac-isc.gc.ca/FederalFundingMain.aspx','status':'source_unavailable'}]}
  row=bc.merge_discovery(old,new);self.assertEqual(row['filings'][0]['href'],old['filings'][0]['href']);self.assertEqual(row['filings'][0]['latestListingStatus'],'source_unavailable')
if __name__=='__main__':unittest.main()
