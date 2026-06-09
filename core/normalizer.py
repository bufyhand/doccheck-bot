from __future__ import annotations

import math
import re
from decimal import Decimal, InvalidOperation
from typing import Any


SPACE_RE = re.compile(r"[\s\u00a0]+")


def clean_text(value: Any) -> str:
    if value is None or _is_nan(value):
        return ""
    return SPACE_RE.sub(" ", str(value)).strip()


def normalize_header(value: Any) -> str:
    return clean_text(value).casefold().replace("ё", "е")


def normalize_barcode(value: Any) -> str:
    text = clean_text(value).replace(" ", "")
    if re.fullmatch(r"\d+\.0", text):
        text = text[:-2]
    return text


def normalize_number(value: Any) -> Decimal | None:
    if value is None or _is_nan(value):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    text = clean_text(value)
    if not text:
        return None
    text = (
        text.replace("₽", "")
        .replace("руб.", "")
        .replace("руб", "")
        .replace("\u00a0", "")
        .replace(" ", "")
        .replace(",", ".")
    )
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def money_equal(left: Decimal | None, right: Decimal | None) -> bool:
    if left is None or right is None:
        return False
    cent = Decimal("0.01")
    return left.quantize(cent) == right.quantize(cent)


def _is_nan(value: Any) -> bool:
    return isinstance(value, float) and math.isnan(value)

