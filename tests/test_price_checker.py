from decimal import Decimal
from unittest import TestCase

from core.models import DocumentRow
from core.price_checker import compare_price


class PriceCheckerTest(TestCase):
    def test_confirmed_package(self):
        order = DocumentRow(
            source="order",
            row_number=1,
            name="Товар, упаковка 10 шт",
            price=Decimal("5"),
        )
        invoice = DocumentRow(
            source="invoice",
            row_number=1,
            name="Товар, упаковка 10 шт",
            price=Decimal("50"),
        )
        status, _ = compare_price(order, invoice)
        self.assertEqual(status, "Цена совпала с учетом упаковки")

