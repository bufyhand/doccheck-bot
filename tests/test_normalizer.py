from decimal import Decimal
from unittest import TestCase

from core.normalizer import normalize_barcode, normalize_number


class NormalizerTest(TestCase):
    def test_barcode(self):
        self.assertEqual(normalize_barcode(" 4680384001303.0 "), "4680384001303")
        self.assertEqual(normalize_barcode("00123"), "00123")

    def test_number(self):
        self.assertEqual(normalize_number("1 250,50 ₽"), Decimal("1250.50"))
        self.assertIsNone(normalize_number(""))

