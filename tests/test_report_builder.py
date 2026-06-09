from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from openpyxl import load_workbook

from core.models import CheckResult, DocumentRow, MatchResult, ParsedDocument
from core.report_builder import build_report


class ReportBuilderTest(TestCase):
    def test_report_v2_columns_combined_sheet_and_small_money_filter(self):
        with TemporaryDirectory() as directory:
            output = Path(directory) / "report.xlsx"
            result = CheckResult(
                order=ParsedDocument(Path("order.xlsx"), "order", 1, {}, []),
                invoice=ParsedDocument(Path("invoice.xlsx"), "invoice", 1, {}, []),
                rows=[
                    MatchResult(
                        status="Проверить вручную",
                        order=_row("order", "Товар мелкая разница", "111", 10, 100, 1000),
                        invoice=_row("invoice", "Товар мелкая разница", "111", 10, 100, 1003),
                        quantity_status="Количество совпало",
                        price_status="Цена совпала",
                        amount_status="Сумма отличается",
                        comment="Суммы строк отличаются при совпавших цене и количестве",
                    ),
                    MatchResult(
                        status="Количество отличается",
                        order=_row("order", "Товар количество", "222", 10, 100, 1000),
                        invoice=_row("invoice", "Товар количество", "222", 8, 100, 800),
                        quantity_status="Количество отличается",
                        price_status="Цена совпала",
                        amount_status="Сумма отличается",
                    ),
                    MatchResult(
                        status="Нет в счете",
                        order=_row("order", "Нет", "333", 1, 50, 50),
                    ),
                    MatchResult(
                        status="Лишнее в счете",
                        invoice=_row("invoice", "Лишнее", "444", 2, 70, 140),
                    ),
                ],
            )

            report = build_report(result, output)
            workbook = load_workbook(report, read_only=True, data_only=True)

            self.assertEqual(
                workbook.sheetnames,
                [
                    "Итог",
                    "Расхождения",
                    "Нет-Лишнее в счете",
                    "Проверить вручную",
                    "Тех_данные",
                ],
            )

            discrepancies = workbook["Расхождения"]
            headers = [cell.value for cell in next(discrepancies.iter_rows(max_row=1))]
            self.assertIn("Разница по количеству", headers)
            self.assertIn("Разница по сумме, ₽", headers)
            self.assertIn("Разница по сумме, %", headers)
            rows = list(discrepancies.iter_rows(min_row=2, values_only=True))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][0], "Количество отличается")
            self.assertEqual(rows[0][8], -2)
            self.assertEqual(rows[0][13], -200)
            self.assertEqual(rows[0][14], "-20.00%")

            missing_extra = workbook["Нет-Лишнее в счете"]
            headers = [cell.value for cell in next(missing_extra.iter_rows(max_row=1))]
            self.assertEqual(headers[0], "Статус")
            statuses = [
                row[0]
                for row in missing_extra.iter_rows(min_row=2, values_only=True)
            ]
            self.assertEqual(statuses, ["Нет в счете", "Лишнее в счете"])

            summary = {
                row[0]: row[1]
                for row in workbook["Итог"].iter_rows(values_only=True)
                if row[0]
            }
            self.assertEqual(
                summary["Скрыто мелких денежных расхождений < 0,5%"], 1
            )
            workbook.close()


def _row(
    source: str,
    name: str,
    barcode: str,
    quantity: int,
    price: int,
    amount: int,
) -> DocumentRow:
    return DocumentRow(
        source=source,
        row_number=1,
        name=name,
        barcode=barcode,
        quantity=Decimal(quantity),
        price=Decimal(price),
        amount=Decimal(amount),
    )
