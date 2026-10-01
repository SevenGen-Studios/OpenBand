import unittest
from tools.local_ocr import coordinate_lines


def box(x, y, width=50, height=12):
    return [[x, y], [x + width, y], [x + width, y + height], [x, y + height]]


class CoordinateRowsTests(unittest.TestCase):
    def test_amounts_remain_with_their_source_row(self):
        items = [(box(300, 11), "100,000"), (box(0, 10), "Education"),
                 (box(400, 10), "90,000"), (box(300, 31), "50,000"),
                 (box(0, 30), "Health")]
        self.assertEqual(coordinate_lines(items), "Education 100,000 90,000\nHealth 50,000")

    def test_wrapped_labels_do_not_merge_adjacent_rows(self):
        self.assertEqual(coordinate_lines([(box(0, 10), "Government"),
                                          (box(0, 25), "funding"),
                                          (box(300, 25), "10,000")]),
                         "Government\nfunding 10,000")

    def test_empty_result(self):
        self.assertEqual(coordinate_lines([]), "")
