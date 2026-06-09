import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from openpyxl import Workbook

from core.catalog import Catalog
from prepare_catalog import prepare_catalog


class CatalogTest(TestCase):
    def test_prepare_catalog_indexes_extra_barcodes_and_conflicts(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "catalog.xlsx"
            output = root / "catalog.json"
            workbook = Workbook()
            sheet = workbook.active
            sheet.append(["Служебная строка"])
            sheet.append(
                [
                    "Наименование товара (услуги, материала)",
                    "Штрих-код",
                    "Дополнительные  штрих-коды",
                ]
            )
            sheet.append(["Товар A", "001", "002, 003"])
            sheet.append(["Товар B", "004", "003"])
            workbook.save(source)

            result = prepare_catalog(source, output)

            self.assertIn("002", result["items"])
            self.assertNotIn("003", result["items"])
            self.assertIn("003", result["conflicts"])
            self.assertEqual(Catalog.load(output).find("002")["name"], "Товар A")
