from __future__ import annotations

import argparse

from core.catalog import Catalog
from core.file_reader import read_document
from core.matcher import reconcile
from core.report_builder import build_report


def check_documents(order_path: str, invoice_path: str, catalog_path: str, output: str):
    catalog = Catalog.load(catalog_path)
    order = read_document(order_path, "order")
    invoice = read_document(invoice_path, "invoice")
    result = reconcile(order, invoice, catalog)
    return result, build_report(result, output)


def main() -> None:
    parser = argparse.ArgumentParser(description="Сверить заказ и счет")
    parser.add_argument("order", help="Excel-файл заказа")
    parser.add_argument("invoice", help="Excel-файл счета")
    parser.add_argument("--catalog", default="data/catalog_index.json")
    parser.add_argument("-o", "--output", default="temp/reports/doccheck_report.xlsx")
    args = parser.parse_args()
    result, report_path = check_documents(
        args.order, args.invoice, args.catalog, args.output
    )
    print(f"Отчет: {report_path}")
    for key, value in result.summary.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()

