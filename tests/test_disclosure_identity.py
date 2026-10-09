import unittest
from tools.review_disclosures import listing_identity


class DisclosureIdentityTests(unittest.TestCase):
    def test_known_isc_migration_does_not_duplicate_existing_document(self):
        old='https://fnp-ppn.aadnc-aandc.gc.ca/fnp/Main/Search/DisplayBinaryData.aspx?BAND_NUMBER_FF=366&FY=2020-2021&DOC=Schedule%20of%20Remuneration%20and%20Expenses&lang=eng'
        current=old.replace('fnp-ppn.aadnc-aandc.gc.ca','services.sac-isc.gc.ca').replace('/Main/','/main/')
        self.assertEqual(listing_identity(old),listing_identity(current))
        self.assertNotEqual(listing_identity(old),listing_identity(current.replace('2020-2021','2022-2023')))
        self.assertNotEqual(listing_identity(old),listing_identity(current.replace('366','367')))

    def test_external_domains_are_not_treated_as_isc(self):
        self.assertNotEqual(listing_identity('https://example.com/source.pdf'),listing_identity('https://other.example/source.pdf'))
