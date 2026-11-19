import copy
import json
import unittest
from pathlib import Path
from lxml import html
from tools.nation_name import nation_name_markup, identity_source_url
from tools.verify_band_numbers import audit, RESEARCH
from tools.audit_provincial_rosters import audit as audit_rosters
from tools.build_site import slugify

ROOT = Path(__file__).resolve().parents[1]


class BandNumberTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bands = json.loads((ROOT / 'data.json').read_text(encoding='utf-8'))['bands']
        cls.roster = json.loads((RESEARCH / 'isc-first-nations.json').read_text(encoding='utf-8'))
        cls.reviewed = json.loads((RESEARCH / 'reviewed-mappings.json').read_text(encoding='utf-8'))

    def test_complete_official_provincial_coverage(self):
        rosters = json.loads((RESEARCH / 'provincial-rosters.json').read_text(encoding='utf-8'))
        result = audit_rosters(self.bands, rosters)
        self.assertFalse(result['completeOfficialCoverage'])
        self.assertEqual([n['iscBandNumber'] for n in result['provinces']['SK']['missingOfficialNations']], [399])
        self.assertEqual({p: row['profileCount'] for p, row in result['provinces'].items()}, {'SK': 69, 'AB': 48, 'MB': 63})
        self.assertEqual(result['provinces']['AB']['sharedAdministrations'][0]['iscBandNumber'], 471)

    def test_unknown_numbers_are_flagged_and_never_inferred(self):
        result = audit(self.bands, self.roster, self.reviewed)
        self.assertEqual(result['verifiedCount'], 180)
        self.assertEqual({row['id'] for row in result['unmatched']}, set())
        for band in self.bands:
            if not band.get('iscBandNumber'):
                self.assertNotIn('nation-band-number', nation_name_markup(band))
                self.assertNotIn('BAND_NUMBER=', identity_source_url(band))
                self.assertEqual(band['filings'], [])

    def test_shared_identities_are_documented_without_copied_financials(self):
        result = audit(self.bands, self.roster, self.reviewed)
        self.assertEqual({row['iscBandNumber'] for row in result['duplicates']}, {462})
        self.assertTrue(all(row['status'] == 'documented_shared_identity' for row in result['duplicates']))
        for band in self.bands:
            if band.get('sharedIscIdentity'):
                self.assertFalse(band['filings'])
                self.assertNotIn('population', band)

    def test_bad_mapping_cannot_pass(self):
        bands = copy.deepcopy(self.bands)
        bands[0]['iscBandNumber'] = bands[1]['iscBandNumber']
        result = audit(bands, self.roster, self.reviewed)
        self.assertTrue(any(row.get('id') == bands[0]['id'] for row in result['unmatched']))
        self.assertTrue(any(row['status'] == 'requires_verification' for row in result['duplicates']))

    def test_all_static_profiles_display_the_database_number(self):
        for band in self.bands:
            page = ROOT / 'first-nations' / slugify(band['name']) / 'index.html'
            document = html.fromstring(page.read_text(encoding='utf-8'))
            heading = document.xpath('//*[@id="profilePrerender"]//h1')[0]
            values = heading.xpath('.//*[@class="nation-band-number"]/text()')
            self.assertEqual(values, [str(band['iscBandNumber']).zfill(3)] if band.get('iscBandNumber') else [])
            self.assertNotIn('BAND_NUMBER=None', page.read_text(encoding='utf-8'))

    def test_markup_escapes_names_and_pads_small_numbers(self):
        markup = nation_name_markup({'name': '<Test & Nation>', 'iscBandNumber': 7})
        self.assertIn('&lt;Test &amp; Nation&gt;', markup)
        self.assertIn('>007</span>', markup)
        self.assertNotIn('nation-band-number', nation_name_markup({'name': 'Unknown', 'id': 399}))
