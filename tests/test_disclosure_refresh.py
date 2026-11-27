from copy import deepcopy
import unittest
from tools.review_disclosures import reconcile_listing

class DisclosureRefreshTests(unittest.TestCase):
    def setUp(self):
        self.placeholder=dict(year='2023-2024',docType='Audited consolidated financial statements',posted=False,href=None,date='Not yet posted',people=[],parse_status='not_required')
        self.band=dict(id=394,iscBandNumber=394,name='Canoe Lake Cree First Nation',filings=[deepcopy(self.placeholder)])
        self.source=dict(self.placeholder,posted=True,href='https://services.sac-isc.gc.ca/fnp/main/Search/DisplayBinaryData.aspx?BAND_NUMBER_FF=394&FY=2023-2024&DOC=Audited%20consolidated%20financial%20statements&lang=eng',date='2026-09-03')

    def test_canoe_lake_placeholder_becomes_posted_without_inventing_figures(self):
        self.assertEqual(len(reconcile_listing(self.band,[self.source])),1)
        filing=self.band['filings'][0]
        self.assertEqual(len(self.band['filings']),1)
        self.assertTrue(filing['posted']);self.assertEqual(filing['date'],'2026-09-03')
        self.assertEqual(filing['people'],[]);self.assertTrue(filing['manual_review_required'])
        self.assertEqual(filing['previousAvailability']['posted'],False)

    def test_actual_isc_listing_contains_both_canoe_lake_documents(self):
        from pathlib import Path
        from tools.ingest_alberta import parse_filings
        raw=(Path(__file__).parent/'fixtures/canoe-lake-2023-2024-listing.html').read_bytes()
        filings=parse_filings(raw,394)
        self.assertEqual(len(filings),2)
        self.assertEqual({f['docType'] for f in filings},{'Audited consolidated financial statements','Schedule of Remuneration and Expenses'})
        self.assertTrue(all(f['date']=='2026-09-03' and f['posted'] for f in filings))
        reconcile_listing(self.band,filings,{'2023-2024'})
        self.assertEqual(len(self.band['filings']),2)
        self.assertTrue(all(f['posted'] and f['href'] for f in self.band['filings']))

    def test_repeat_refresh_is_idempotent(self):
        reconcile_listing(self.band,[self.source]);self.assertEqual(reconcile_listing(self.band,[self.source]),[])
        self.assertEqual(len(self.band['filings']),1)

    def test_new_audit_and_pay_statuses_survive_sanitization(self):
        from tools.sanitize_data import sanitize_data
        for doc_type in ('Audited consolidated financial statements','Schedule of Remuneration and Expenses'):
            source=deepcopy(self.source)
            source['href']=source['href'].replace('Audited%20consolidated%20financial%20statements',doc_type.replace(' ','%20'))
            source['docType']=doc_type
            band=dict(id=394,iscBandNumber=394,filings=[])
            reconcile_listing(band,[source])
            before=deepcopy(band)
            sanitize_data({'bands':[band]})
            self.assertEqual(band,before)
            filing=band['filings'][0]
            self.assertTrue(filing['manual_review_required'])
            self.assertEqual(filing['verificationStatus'],'source_listed_pending_extraction')
            self.assertEqual(filing['parse_status'],'not_required' if doc_type.startswith('Audited') else 'pending_manual_review')
            if doc_type.startswith('Audited'):
                self.assertEqual(filing['technical_status'],'pending_manual_review')

    def test_parsed_values_and_source_are_preserved(self):
        self.band['filings'][0].update(posted=True,href='https://original.example/a.pdf',people=[{'name':'Original','remuneration':10}],parse_status='ok_pdf_text')
        original=deepcopy(self.band);self.assertEqual(reconcile_listing(self.band,[self.source]),[])
        self.assertEqual(self.band,original)

    def test_year_filter_preserves_other_years(self):
        original=deepcopy(self.band)
        self.assertEqual(reconcile_listing(self.band,[self.source],{'2024-2025'}),[]);self.assertEqual(self.band,original)

    def test_wrong_nation_or_year_rejected(self):
        for source in [dict(self.source,href=self.source['href'].replace('394','395')),dict(self.source,year='2024-2025')]:
            with self.assertRaises(ValueError):reconcile_listing(self.band,[source])

    def test_absent_source_does_not_downgrade_posted_record(self):
        reconcile_listing(self.band,[self.source]);original=deepcopy(self.band)
        reconcile_listing(self.band,[]);self.assertEqual(self.band,original)

if __name__=='__main__':unittest.main()
