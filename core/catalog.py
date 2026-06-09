from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.normalizer import normalize_barcode


class CatalogError(RuntimeError):
    pass


@dataclass(slots=True)
class Catalog:
    items_by_barcode: dict[str, dict[str, Any]]
    conflicts: dict[str, list[dict[str, Any]]]

    @classmethod
    def load(cls, path: str | Path) -> "Catalog":
        catalog_path = Path(path)
        if not catalog_path.exists():
            raise CatalogError(
                "Машинный справочник номенклатуры не найден: "
                f"{catalog_path}."
            )
        with catalog_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        if "items" in data:
            return cls(data["items"], data.get("conflicts", {}))
        return cls(data, {})

    def find(self, barcode: str) -> dict[str, Any] | None:
        normalized = normalize_barcode(barcode)
        if not normalized or normalized in self.conflicts:
            return None
        return self.items_by_barcode.get(normalized)

    @property
    def barcode_count(self) -> int:
        return len(self.items_by_barcode)

