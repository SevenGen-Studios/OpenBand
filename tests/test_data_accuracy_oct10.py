import copy
import json
import unittest
from pathlib import Path

from tools.apply_manual_overrides import apply_record, iter_override_records, reviewed_source_protected
from tools.sanitize_data import sanitize_data

ROOT = Path(__file__).resolve().parents[1]


class OctoberSourceReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((ROOT / 'data.json').read_text())

    def filing(self, data, band_id, year):
        return next(f for b in data['bands'] if str(b['id']) == band_id
                    for f in b['filings'] if f['year'] == year and 'remuneration' in f['docType'].lower())

    def test_cowessess_subtotals_are_not_extra_payments(self):
        for year, expected, salary, other, expenses in [
            ('2016-2017', 424283, 302683, 9000, 112600),
            ('2018-2019', 622592, 423033, 4005, 195554),
        ]:
            f = self.filing(self.data, '361', year)
            rows = f['people']
            self.assertEqual(sum(p['total'] for p in rows), expected)
            self.assertEqual(sum(p['remuneration'] for p in rows), salary)
            self.assertEqual(sum(p['otherPayments'] for p in rows), other)
            self.assertEqual(sum((p.get('travel') or 0) + (p.get('expenses') or 0) for p in rows), expenses)
            for p in rows:
                self.assertEqual(p['total'], p['reportedRemunerationSubtotal'] + (p.get('travel') or 0) + (p.get('expenses') or 0))
                self.assertEqual(p['sourceSubtotalDifference'], 0)

    def test_source_arithmetic_conflicts_are_withheld_and_preserved(self):
        for year, gap in [('2019-2020', 685), ('2022-2023', 10610)]:
            f = self.filing(self.data, '361', year)
            self.assertEqual(f['people'], [])
            self.assertTrue(f['manual_review_required'])
            self.assertEqual(f['parse_status'], 'pending_manual_review')
            self.assertEqual(f['source_review']['status'], 'source_arithmetic_conflict')
            self.assertEqual(sum(r['difference'] for r in f['source_review']['discrepancies']), gap)
            self.assertTrue(f['source_review']['rows'])
            self.assertTrue(reviewed_source_protected(f))
        newer = self.filing(self.data, '361', '2022-2023')
        row = next(p for p in newer['source_review']['rows'] if p['name'] == 'Richard Aisaican')
        self.assertEqual(row['reportedRemunerationSubtotal'], 76161)
        self.assertEqual(row['remuneration'] + row['otherPayments'], 65551)

    def test_day_star_current_total_and_wrapped_name(self):
        f = self.filing(self.data, '389', '2013-2014')
        rows = f['people']
        self.assertEqual([sum(p[k] for p in rows) for k in ('remuneration', 'travel', 'otherPayments', 'total')],
                         [166277, 37281, 13343, 216901])
        self.assertTrue(any(p['name'] == 'David Crow Buffalo' for p in rows))
        self.assertTrue(all(p['creditCard'] is None for p in rows))
        self.assertTrue(all(not p['comparativeDisclosure']['includedInCurrentTotal'] for p in rows))

    def test_carry_the_kettle_expenses_and_card_are_distinct(self):
        f = self.filing(self.data, '378', '2022-2023')
        chief = next(p for p in f['people'] if p['role'] == 'Chief')
        self.assertEqual(chief['expenses'], 123723)
        self.assertEqual(chief['creditCard'], 61030)
        self.assertIsNone(chief['travel'])
        self.assertEqual(chief['total'], 274426)
        self.assertEqual(sum(p['total'] for p in f['people']), 955831)
        self.assertEqual(f['manualSourceReview']['reportedColumnTotals']['total'], 955832)

    def test_all_overrides_and_sanitizer_preserve_this_batch(self):
        data = copy.deepcopy(self.data)
        pairs = [('361', '2016-2017'), ('361', '2018-2019'), ('361', '2019-2020'),
                 ('361', '2022-2023'), ('389', '2013-2014'), ('378', '2022-2023')]
        before = {pair: copy.deepcopy(self.filing(data, *pair)) for pair in pairs}
        for path in sorted((ROOT / 'manual_overrides').glob('*.json')):
            for record in iter_override_records(path):
                apply_record(data, record)
        sanitize_data(data)
        for pair in pairs:
            with self.subTest(pair=pair):
                self.assertEqual(self.filing(data, *pair), before[pair])

    def test_source_review_cannot_bind_to_a_different_year_or_document(self):
        record = next(iter_override_records(ROOT / 'manual_overrides/2026_10_10_source_review_batch.json'))
        year = next(iter(record['sourceReviews']))
        band = next(b for b in self.data['bands'] if b['name'] == record['band'])
        f = copy.deepcopy(self.filing(self.data, str(band['id']), year))
        f.pop('manualSourceReview')
        for field, wrong in [('year', '2000-2001'), ('sourcePdf', 'https://example.com/wrong.pdf'), ('sha256', 'bad')]:
            bad = copy.deepcopy(record)
            bad['sourceReviews'][year][field] = wrong
            data = {'bands': [{'name': record['band'], 'filings': [copy.deepcopy(f)]}]}
            with self.assertRaisesRegex(ValueError, 'provenance mismatch'):
                apply_record(data, bad)


if __name__ == '__main__':
    unittest.main()
