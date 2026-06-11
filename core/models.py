from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class DocumentRow:
    source: str
    row_number: int
    name: str = ""
    article: str = ""
    barcode: str = ""
    unit: str = ""
    quantity: Decimal | None = None
    price: Decimal | None = None
    amount: Decimal | None = None
    discount: Decimal | None = None
    item_id: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ParsedDocument:
    path: Path
    source: str
    header_row: int
    columns: dict[str, str]
    rows: list[DocumentRow]


@dataclass(slots=True)
class MatchResult:
    status: str
    order: DocumentRow | None = None
    invoice: DocumentRow | None = None
    quantity_status: str = ""
    price_status: str = ""
    amount_status: str = ""
    comment: str = ""
    technical_comment: str = ""

    def to_context(self) -> dict[str, Any]:
        def row_data(row: DocumentRow | None) -> dict[str, Any] | None:
            if row is None:
                return None
            data = asdict(row)
            for key in ("quantity", "price", "amount"):
                data[key] = str(data[key]) if data[key] is not None else None
            data.pop("raw", None)
            return data

        return {
            "status": self.status,
            "order": row_data(self.order),
            "invoice": row_data(self.invoice),
            "quantity_status": self.quantity_status,
            "price_status": self.price_status,
            "amount_status": self.amount_status,
            "comment": self.comment,
            "technical_comment": self.technical_comment,
        }


@dataclass(slots=True)
class CheckResult:
    order: ParsedDocument
    invoice: ParsedDocument
    rows: list[MatchResult]

    @property
    def summary(self) -> dict[str, int]:
        statuses: dict[str, int] = {}
        for row in self.rows:
            statuses[row.status] = statuses.get(row.status, 0) + 1
        return {
            "Строк в заказе": len(self.order.rows),
            "Строк в счете": len(self.invoice.rows),
            "Сопоставлено": sum(1 for row in self.rows if row.order and row.invoice),
            "ОК": statuses.get("ОК", 0),
            "Цена отличается": statuses.get("Цена отличается", 0),
            "Сумма отличается": statuses.get("Сумма отличается", 0),
            "Количество отличается": statuses.get("Количество отличается", 0),
            "Цена и количество отличаются": statuses.get(
                "Цена и количество отличаются", 0
            ),
            "Нет в счете": statuses.get("Нет в счете", 0),
            "Лишнее в счете": statuses.get("Лишнее в счете", 0),
            "Проверить вручную": sum(
                count
                for status, count in statuses.items()
                if "проверить вручную" in status.lower()
                or status in {"Штрихкод не найден", "Ошибка данных"}
            ),
        }

    def to_context(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "rows": [row.to_context() for row in self.rows],
        }
