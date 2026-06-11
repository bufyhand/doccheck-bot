from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from core.catalog import Catalog
from core.models import CheckResult, DocumentRow, MatchResult, ParsedDocument
from core.price_checker import compare_amount, compare_price


def reconcile(
    order: ParsedDocument, invoice: ParsedDocument, catalog: Catalog
) -> CheckResult:
    order_by_item, order_unmatched, order_manual = _index_rows(order.rows, catalog)
    invoice_by_item, invoice_unmatched, invoice_manual = _index_rows(invoice.rows, catalog)
    invoice_by_item, item_aggregation_manual = _aggregate_indexed_invoice_rows(invoice_by_item)
    invoice_unmatched, barcode_aggregation_manual = _aggregate_unmatched_invoice_rows(
        invoice_unmatched
    )
    direct_results, order_unmatched, invoice_unmatched = _match_same_barcodes(
        order_unmatched, invoice_unmatched
    )
    results = (
        order_manual
        + invoice_manual
        + item_aggregation_manual
        + barcode_aggregation_manual
        + direct_results
    )
    results.extend(_unmatched_to_manual(order_unmatched))
    results.extend(_unmatched_to_manual(invoice_unmatched))

    all_item_ids = set(order_by_item) | set(invoice_by_item)
    for item_id in sorted(all_item_ids):
        order_rows = order_by_item.get(item_id, [])
        invoice_rows = invoice_by_item.get(item_id, [])
        if len(order_rows) > 1 or len(invoice_rows) > 1:
            for row in order_rows + invoice_rows:
                results.append(
                    MatchResult(
                        status="Проверить вручную",
                        order=row if row.source == "order" else None,
                        invoice=row if row.source == "invoice" else None,
                        comment="Дубль или неоднозначное сопоставление item_id",
                        technical_comment="Дубль или неоднозначное сопоставление item_id",
                    )
                )
            continue
        if not order_rows:
            results.append(
                MatchResult(
                    status="Лишнее в счете",
                    invoice=invoice_rows[0],
                    comment="Позиция найдена в справочнике, но отсутствует в заказе",
                    technical_comment="Позиция найдена в справочнике, но отсутствует в заказе",
                )
            )
            continue
        if not invoice_rows:
            results.append(
                MatchResult(
                    status="Нет в счете",
                    order=order_rows[0],
                    comment="Позиция найдена в справочнике, но отсутствует в счете",
                    technical_comment="Позиция найдена в справочнике, но отсутствует в счете",
                )
            )
            continue
        results.append(_compare_pair(order_rows[0], invoice_rows[0]))

    return CheckResult(order=order, invoice=invoice, rows=results)


def _index_rows(
    rows: list[DocumentRow], catalog: Catalog
) -> tuple[dict[str, list[DocumentRow]], list[DocumentRow], list[MatchResult]]:
    indexed: dict[str, list[DocumentRow]] = defaultdict(list)
    unmatched: list[DocumentRow] = []
    manual: list[MatchResult] = []
    for row in rows:
        result_kwargs = {
            "order": row if row.source == "order" else None,
            "invoice": row if row.source == "invoice" else None,
        }
        if row.errors:
            manual.append(
                MatchResult(
                    status="Ошибка данных",
                    comment="; ".join(row.errors),
                    technical_comment="; ".join(row.errors),
                    **result_kwargs,
                )
            )
            continue
        item = catalog.find(row.barcode)
        if item is None:
            unmatched.append(row)
            continue
        row.item_id = str(item["item_id"])
        indexed[row.item_id].append(row)
    return indexed, unmatched, manual


def _match_same_barcodes(
    order_rows: list[DocumentRow], invoice_rows: list[DocumentRow]
) -> tuple[list[MatchResult], list[DocumentRow], list[DocumentRow]]:
    order_by_barcode = _group_by_barcode(order_rows)
    invoice_by_barcode = _group_by_barcode(invoice_rows)
    results: list[MatchResult] = []
    matched_order: set[int] = set()
    matched_invoice: set[int] = set()

    for barcode in sorted(set(order_by_barcode) & set(invoice_by_barcode)):
        orders = order_by_barcode[barcode]
        invoices = invoice_by_barcode[barcode]
        if len(orders) == 1 and len(invoices) == 1:
            result = _compare_pair(orders[0], invoices[0])
            result.comment = _join_comments(
                result.comment,
                "Штрихкод отсутствует в справочнике, строки сопоставлены напрямую по одинаковому штрихкоду",
            )
            result.technical_comment = _join_comments(
                result.technical_comment,
                "Штрихкод отсутствует в справочнике, строки сопоставлены напрямую по одинаковому штрихкоду",
            )
            results.append(result)
            matched_order.add(id(orders[0]))
            matched_invoice.add(id(invoices[0]))
        else:
            for row in orders + invoices:
                results.append(
                    MatchResult(
                        status="Проверить вручную",
                        order=row if row.source == "order" else None,
                        invoice=row if row.source == "invoice" else None,
                        comment=(
                            "Штрихкод отсутствует в справочнике и встречается "
                            "несколько раз в заказе или счете"
                        ),
                        technical_comment=(
                            "Штрихкод отсутствует в справочнике и встречается "
                            "несколько раз в заказе или счете"
                        ),
                    )
                )
                if row.source == "order":
                    matched_order.add(id(row))
                else:
                    matched_invoice.add(id(row))

    return (
        results,
        [row for row in order_rows if id(row) not in matched_order],
        [row for row in invoice_rows if id(row) not in matched_invoice],
    )


def _group_by_barcode(rows: list[DocumentRow]) -> dict[str, list[DocumentRow]]:
    grouped: dict[str, list[DocumentRow]] = defaultdict(list)
    for row in rows:
        if row.barcode:
            grouped[row.barcode].append(row)
    return grouped


def _unmatched_to_manual(rows: list[DocumentRow]) -> list[MatchResult]:
    results: list[MatchResult] = []
    for row in rows:
        results.append(
            MatchResult(
                status="Штрихкод не найден",
                order=row if row.source == "order" else None,
                invoice=row if row.source == "invoice" else None,
                comment="Штрихкод не найден в справочнике или является конфликтным",
                technical_comment="Штрихкод не найден в справочнике или является конфликтным",
            )
        )
    return results


def _aggregate_indexed_invoice_rows(
    indexed: dict[str, list[DocumentRow]]
) -> tuple[dict[str, list[DocumentRow]], list[MatchResult]]:
    aggregated: dict[str, list[DocumentRow]] = {}
    manual: list[MatchResult] = []
    for item_id, rows in indexed.items():
        if len(rows) == 1:
            aggregated[item_id] = rows
            continue
        aggregate, error = _aggregate_invoice_group(
            rows, group_id=f"item_id:{item_id}", key_type="item_id"
        )
        if error:
            for row in rows:
                manual.append(
                    MatchResult(
                        status="Проверить вручную",
                        invoice=row,
                        comment=error,
                        technical_comment=error,
                    )
                )
        else:
            aggregated[item_id] = [aggregate]
    return aggregated, manual


def _aggregate_unmatched_invoice_rows(
    rows: list[DocumentRow],
) -> tuple[list[DocumentRow], list[MatchResult]]:
    grouped = _group_by_barcode(rows)
    result_rows: list[DocumentRow] = []
    manual: list[MatchResult] = []
    handled: set[int] = set()
    for barcode, group in grouped.items():
        if len(group) == 1:
            continue
        aggregate, error = _aggregate_invoice_group(
            group, group_id=f"barcode:{barcode}", key_type="normalized_barcode"
        )
        if error:
            for row in group:
                manual.append(
                    MatchResult(
                        status="Проверить вручную",
                        invoice=row,
                        comment=error,
                        technical_comment=error,
                    )
                )
                handled.add(id(row))
        else:
            result_rows.append(aggregate)
            handled.update(id(row) for row in group)
    result_rows.extend(row for row in rows if id(row) not in handled)
    return result_rows, manual


def _aggregate_invoice_group(
    rows: list[DocumentRow], group_id: str, key_type: str
) -> tuple[DocumentRow | None, str]:
    if any(row.quantity is None for row in rows):
        return None, "Проблемная агрегация: в группе есть строки без количества"
    if any(row.amount is None for row in rows):
        return None, "Проблемная агрегация: в группе есть строки без суммы"
    first = rows[0]
    quantity = sum((row.quantity for row in rows), Decimal("0"))
    amount = sum((row.amount for row in rows), Decimal("0"))
    price = (amount / quantity).quantize(Decimal("0.01")) if quantity else first.price
    aggregate = DocumentRow(
        source="invoice",
        row_number=first.row_number,
        name=first.name,
        article=first.article,
        barcode=first.barcode,
        unit=first.unit,
        quantity=quantity,
        price=price,
        amount=amount,
        discount=sum(
            (row.discount for row in rows if row.discount is not None), Decimal("0")
        )
        or None,
        item_id=first.item_id,
        raw=dict(first.raw),
        errors=[],
    )
    aggregate.raw.update(
        {
            "aggregation_group_id": group_id,
            "aggregation_key_type": key_type,
            "aggregation_status": "success",
            "aggregation_rows_count": str(len(rows)),
            "aggregation_source_rows": ", ".join(str(row.row_number) for row in rows),
            "aggregation_barcodes": ", ".join(
                sorted({row.barcode for row in rows if row.barcode})
            ),
            "aggregation_total_quantity": str(quantity),
            "aggregation_total_amount": str(amount),
        }
    )
    return aggregate, ""


def _compare_pair(order: DocumentRow, invoice: DocumentRow) -> MatchResult:
    quantity_status = (
        "Количество совпало"
        if order.quantity is not None
        and invoice.quantity is not None
        and order.quantity == invoice.quantity
        else "Количество отличается"
    )
    price_status, price_comment = compare_price(order, invoice)
    amount_status, amount_comment = compare_amount(order, invoice)
    comments = [text for text in (price_comment, amount_comment) if text]

    if amount_status == "Проверить вручную" or price_status in {
        "Возможна упаковка, проверить вручную",
        "Проверить цену вручную",
    }:
        status = (
            "Возможна упаковка, проверить вручную"
            if price_status == "Возможна упаковка, проверить вручную"
            else "Проверить вручную"
        )
    elif quantity_status == "Количество отличается":
        status = (
            "Цена и количество отличаются"
            if price_status == "Цена отличается"
            else "Количество отличается"
        )
    elif amount_status == "Сумма отличается":
        status = "Сумма отличается"
        comments.append("Суммы строк отличаются при совпавшем количестве")
    elif amount_status == "Сумма совпала":
        status = "ОК"
    elif price_status == "Цена совпала с учетом упаковки":
        status = price_status
    elif price_status == "Цена отличается":
        status = "Цена отличается"
    else:
        status = "ОК"

    if order.barcode != invoice.barcode:
        comments.append("Разные штрихкоды ведут к одному item_id")
    if invoice.raw.get("aggregation_status") == "success" and status != "ОК":
        comments.append(
            "Позиция объединена по повторяющемуся штрихкоду в счете, но количество или сумма отличаются"
        )
    return MatchResult(
        status=status,
        order=order,
        invoice=invoice,
        quantity_status=quantity_status,
        price_status=price_status,
        amount_status=amount_status,
        comment="; ".join(comments),
        technical_comment="; ".join(comments),
    )


def _join_comments(*comments: str) -> str:
    return "; ".join(comment for comment in comments if comment)
