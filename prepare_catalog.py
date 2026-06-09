from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from core.normalizer import clean_text, normalize_barcode, normalize_header


ALIASES = {
    "name": {"наименование товара", "наименование", "товар"},
    "main_barcode": {"штрих-код", "штрихкод", "основной штрих-код"},
    "extra_barcodes": {"дополнительные штрих-коды", "дополнительные штрихкоды"},
}


def prepare_catalog(source: str | Path, output: str | Path) -> dict:
    frame = pd.read_excel(source, header=None, dtype=object)
    header_row, columns = _find_header(frame)
    missing = {"name", "main_barcode", "extra_barcodes"} - columns.keys()
    if missing:
        raise ValueError(f"Не найдены колонки справочника: {', '.join(sorted(missing))}")

    by_barcode: dict[str, list[dict]] = {}
    item_number = 0
    for row_index in range(header_row + 1, len(frame)):
        row = frame.iloc[row_index]
        name = clean_text(row.iloc[columns["name"]])
        main = normalize_barcode(row.iloc[columns["main_barcode"]])
        extras = [
            normalize_barcode(value)
            for value in clean_text(row.iloc[columns["extra_barcodes"]]).split(",")
        ]
        barcodes = list(dict.fromkeys(code for code in [main, *extras] if code))
        if not name or not barcodes:
            continue
        item_number += 1
        item = {
            "item_id": f"item_{item_number:06d}",
            "name": name,
            "main_barcode": main or barcodes[0],
            "all_barcodes": barcodes,
        }
        for barcode in barcodes:
            by_barcode.setdefault(barcode, []).append(item)

    conflicts = {
        barcode: items for barcode, items in by_barcode.items() if len(items) > 1
    }
    items = {
        barcode: values[0]
        for barcode, values in by_barcode.items()
        if barcode not in conflicts
    }
    result = {"items": items, "conflicts": conflicts}
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result


def _find_header(frame: pd.DataFrame) -> tuple[int, dict[str, int]]:
    normalized_aliases = {
        field: {normalize_header(alias) for alias in values}
        for field, values in ALIASES.items()
    }
    best_match: tuple[int, dict[str, int]] = (0, {})
    for row_index in range(min(len(frame), 100)):
        columns = {}
        for column_index, value in enumerate(frame.iloc[row_index]):
            header = normalize_header(value)
            for field, aliases in normalized_aliases.items():
                if any(_header_matches(header, alias) for alias in aliases):
                    columns[field] = column_index
        if len(columns) > len(best_match[1]):
            best_match = (row_index, columns)
        if {"name", "main_barcode", "extra_barcodes"}.issubset(columns):
            return row_index, columns
    return best_match


def _header_matches(header: str, alias: str) -> bool:
    if header == alias:
        return True
    # Реальные выгрузки часто дополняют базовый заголовок пояснением в скобках.
    return header.startswith(f"{alias} ") or header.startswith(f"{alias}(")


def main() -> None:
    parser = argparse.ArgumentParser(description="Подготовить catalog_index.json")
    parser.add_argument("source", help="Исходный Excel-справочник")
    parser.add_argument(
        "-o", "--output", default="data/catalog_index.json", help="Выходной JSON"
    )
    args = parser.parse_args()
    result = prepare_catalog(args.source, args.output)
    print(
        f"Готово: {len(result['items'])} штрихкодов, "
        f"{len(result['conflicts'])} конфликтов."
    )


if __name__ == "__main__":
    main()
