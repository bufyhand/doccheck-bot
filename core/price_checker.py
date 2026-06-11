from __future__ import annotations

import re
from decimal import Decimal

from core.models import DocumentRow
from core.normalizer import money_equal


PACK_RE = re.compile(
    r"(?:уп\.?\s*)?(\d{1,4})\s*(?:шт|штук)|(?:упак(?:овка)?|пакет)\s*(\d{1,4})",
    re.IGNORECASE,
)


def compare_price(order: DocumentRow, invoice: DocumentRow) -> tuple[str, str]:
    if order.price is None or invoice.price is None:
        return "Проверить цену вручную", "Цена отсутствует или не читается"
    if money_equal(order.price, invoice.price):
        return "Цена совпала", ""

    multiplicities = {
        number
        for text in (order.name, invoice.name)
        for number in _extract_multiplicities(text)
    }
    for multiplicity in multiplicities:
        factor = Decimal(multiplicity)
        if money_equal(order.price * factor, invoice.price) or money_equal(
            invoice.price * factor, order.price
        ):
            return (
                "Цена совпала с учетом упаковки",
                f"В наименовании подтверждена кратность упаковки: {multiplicity}",
            )

    if _looks_like_integer_ratio(order.price, invoice.price):
        return (
            "Возможна упаковка, проверить вручную",
            "Цены отличаются примерно в целое число раз, но кратность не подтверждена",
        )
    return "Цена отличается", ""


def compare_amount(order: DocumentRow, invoice: DocumentRow) -> tuple[str, str]:
    if order.amount is None or invoice.amount is None:
        return "Сумма отсутствует", ""
    if money_equal(order.amount, invoice.amount):
        return "Сумма совпала", ""
    return "Сумма отличается", ""


def _extract_multiplicities(text: str) -> set[int]:
    result: set[int] = set()
    for match in PACK_RE.finditer(text):
        value = match.group(1) or match.group(2)
        if value and int(value) > 1:
            result.add(int(value))
    return result


def _looks_like_integer_ratio(left: Decimal, right: Decimal) -> bool:
    if left <= 0 or right <= 0:
        return False
    ratio = max(left, right) / min(left, right)
    nearest = ratio.quantize(Decimal("1"))
    return nearest > 1 and abs(ratio - nearest) <= Decimal("0.02")
