from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

import pandas as pd

from core.models import DocumentRow, ParsedDocument
from core.normalizer import clean_text, normalize_barcode, normalize_header, normalize_number


class DocumentReadError(RuntimeError):
    pass


COLUMN_ALIASES = {
    "barcode": ["Штрихкод", "Штрих-код", "ШК", "Barcode", "EAN", "Unit EAN", "Номенкл.номер", "Номенклатурный номер"],
    "name": ["Наименование", "Наименование товара", "Товар", "Название", "Номенклатура", "Описание"],
    "article": ["Артикул", "Код", "Код товара", "Код поставщика", "Артикул поставщика", "Но.", "No.", "Номер"],
    "quantity": ["Кол-во", "Количество", "Коли-чество", "Кол.", "Qty"],
    "price": ["Цена", "Цена, РУБ", "Цена со скидкой", "Цена поставщика", "Цена закупки", "Цена Единицы", "Цена (тариф)"],
    "amount": ["Сумма", "Сумма, РУБ", "Сумма (руб)", "Итого", "Стоимость"],
    "discount": ["Скидка", "Скидка, РУБ", "Сумма скидки"],
    "unit": ["Ед. изм.", "Ед. измерения", "Единица", "Ед."],
}
NORMALIZED_ALIASES = {
    field: {normalize_header(alias) for alias in aliases}
    for field, aliases in COLUMN_ALIASES.items()
}
REQUIRED_FIELDS = {"quantity", "price"}
EAN_RE = re.compile(r"(?:unit\s*)?ean\s*[:№#-]?\s*(\d{6,20})", re.IGNORECASE)


def read_document(path: str | Path, source: str) -> ParsedDocument:
    document_path = Path(path)
    if document_path.suffix.lower() not in {".xlsx", ".xls"}:
        raise DocumentReadError("Поддерживаются только файлы .xlsx и .xls.")
    try:
        raw = pd.read_excel(document_path, header=None, dtype=object)
    except Exception as exc:
        raise DocumentReadError(
            "Не удалось прочитать файл. Проверьте формат файла."
        ) from exc

    header_row, columns = _find_header(raw)
    missing = REQUIRED_FIELDS - columns.keys()
    if "barcode" not in columns and "name" not in columns:
        missing.add("barcode")
    if missing:
        labels = ", ".join(sorted(missing))
        raise DocumentReadError(f"Не удалось найти обязательные колонки: {labels}.")

    rows: list[DocumentRow] = []
    for index in range(header_row + 1, len(raw)):
        values = raw.iloc[index]
        if all(clean_text(value) == "" for value in values):
            continue
        mapped = {
            field: values.iloc[column_index]
            for field, column_index in columns.items()
        }
        extracted_barcode = normalize_barcode(mapped.get("barcode")) or _extract_ean(
            values
        )
        if _is_barcode_continuation(mapped, values) and rows:
            rows[-1].barcode = extracted_barcode
            rows[-1].errors = [
                error for error in rows[-1].errors if error != "Штрихкод пустой"
            ]
            rows[-1].raw["barcode_from_continuation_row"] = str(index + 1)
            continue
        quantity = normalize_number(mapped.get("quantity"))
        amount = normalize_number(mapped.get("amount"))
        discount = normalize_number(mapped.get("discount"))
        price = normalize_number(mapped.get("price"))
        if discount is not None and amount is not None and quantity not in {None, 0}:
            price = (amount / quantity).quantize(Decimal("0.01"))
        row = DocumentRow(
            source=source,
            row_number=index + 1,
            name=clean_text(mapped.get("name")),
            article=clean_text(mapped.get("article")),
            barcode=extracted_barcode,
            unit=clean_text(mapped.get("unit")),
            quantity=quantity,
            price=price,
            amount=amount,
            discount=discount,
            raw={str(key): clean_text(value) for key, value in mapped.items()},
        )
        if _is_non_product_row(row):
            continue
        if not row.barcode:
            row.errors.append("Штрихкод пустой")
        if row.quantity is None:
            row.errors.append("Количество не является числом")
        if row.price is None:
            row.errors.append("Цена не является числом")
        rows.append(row)

    return ParsedDocument(
        path=document_path,
        source=source,
        header_row=header_row + 1,
        columns={field: clean_text(raw.iloc[header_row, index]) for field, index in columns.items()},
        rows=rows,
    )


def _find_header(frame: pd.DataFrame) -> tuple[int, dict[str, int]]:
    best: tuple[int, dict[str, int]] | None = None
    for row_index in range(min(len(frame), 100)):
        columns: dict[str, int] = {}
        scores: dict[str, int] = {}
        for column_index, value in enumerate(frame.iloc[row_index]):
            header = normalize_header(value)
            for field, aliases in NORMALIZED_ALIASES.items():
                score = _header_score(field, header, aliases)
                if score > scores.get(field, 0):
                    columns[field] = column_index
                    scores[field] = score
        if best is None or len(columns) > len(best[1]):
            best = (row_index, columns)
        if REQUIRED_FIELDS.issubset(columns):
            return row_index, columns
    return best or (0, {})


def _header_score(field: str, header: str, aliases: set[str]) -> int:
    if not _header_matches(header, aliases):
        return 0
    score = 10
    compact = _compact_header(header)
    if field == "amount":
        if compact == "сумма":
            score += 30
        if "безскидки" in compact:
            score -= 15
        if "сналогом" in compact:
            score += 20
        if "безналога" in compact:
            score -= 5
        if "сумманалога" in compact:
            score -= 10
    return score


def _header_matches(header: str, aliases: set[str]) -> bool:
    collapsed = header.replace("\n", " ").replace("-", "")
    compact = _compact_header(header)
    return any(
        header == alias
        or header.startswith(f"{alias} ")
        or header.startswith(f"{alias}(")
        or collapsed == alias.replace("-", "")
        or collapsed.startswith(f"{alias.replace('-', '')} ")
        or collapsed.startswith(f"{alias.replace('-', '')}(")
        or compact == _compact_header(alias)
        or compact.startswith(_compact_header(alias))
        for alias in aliases
    )


def _compact_header(value: str) -> str:
    return re.sub(r"[\s\-\u00a0]+", "", value)


def _extract_ean(values) -> str:
    for value in values:
        match = EAN_RE.search(clean_text(value))
        if match:
            return normalize_barcode(match.group(1))
    return ""


def _is_barcode_continuation(mapped: dict[str, object], values) -> bool:
    if not _extract_ean(values):
        return False
    return (
        normalize_number(mapped.get("quantity")) is None
        and normalize_number(mapped.get("price")) is None
        and normalize_number(mapped.get("amount")) is None
    )


def _is_non_product_row(row: DocumentRow) -> bool:
    barcode = normalize_barcode(row.barcode)
    if barcode and not barcode.isdigit():
        return True
    if not barcode and _looks_like_column_code_row(row):
        return True
    return (
        row.quantity is None
        and row.price is None
        and row.amount is None
        and not barcode
    )


def _looks_like_column_code_row(row: DocumentRow) -> bool:
    name = clean_text(row.name).casefold()
    article = clean_text(row.article).casefold()
    return (
        name in {"1", "1а", "1a"}
        or article in {"а", "a", "б", "b"}
    ) and (
        row.quantity is not None
        or row.price is not None
        or row.amount is not None
    )
