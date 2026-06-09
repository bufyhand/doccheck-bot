from pathlib import Path
from unittest import TestCase

from core.gigachat_client import GigaChatClient
from core.models import CheckResult, DocumentRow, MatchResult, ParsedDocument


class GigaChatSummaryTest(TestCase):
    def test_fallback_summary_uses_fixed_report_shape(self):
        result = CheckResult(
            order=ParsedDocument(Path("order.xlsx"), "order", 1, {}, []),
            invoice=ParsedDocument(Path("invoice.xlsx"), "invoice", 1, {}, []),
            rows=[
                MatchResult(
                    status="Цена отличается",
                    order=DocumentRow("order", 2, name="Товар", barcode="1"),
                    invoice=DocumentRow("invoice", 2, name="Товар", barcode="1"),
                ),
                MatchResult(
                    status="Нет в счете",
                    order=DocumentRow("order", 3, name="Нет", barcode="2"),
                ),
            ],
        )

        summary = GigaChatClient().fallback_summary(result)

        self.assertIn("Резюме сверки", summary)
        self.assertIn("1. Итог по файлам", summary)
        self.assertIn("2. Что требует внимания", summary)
        self.assertIn("3. Акценты", summary)
        self.assertIn("4. Следующий шаг", summary)
        self.assertIn("Можете задать вопрос", summary)
        self.assertIn("Цена отличается: 1", summary)
        self.assertIn("Нет в счете: 1", summary)
