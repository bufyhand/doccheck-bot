from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from core.models import CheckResult, MatchResult


SYSTEM_RULES = """
Ты аналитический помощник DocCheck Manager Bot.
Отвечай только на основе переданного результата текущей сверки.
Не меняй статусы, не сопоставляй товары самостоятельно, не пересчитывай итог
вместо алгоритма и никогда не утверждай, что счет можно согласовать или оплатить.
Пиши кратко по-русски и явно отмечай необходимость ручной проверки.
Для резюме возвращай только блок "Акценты", без приветствия и без Markdown-таблиц.
""".strip()


class GigaChatClient:
    def __init__(self) -> None:
        self.credentials = os.getenv("GIGACHAT_CREDENTIALS", "")
        self.scope = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
        self.model = os.getenv("GIGACHAT_MODEL", "GigaChat")
        self.verify_ssl = os.getenv("GIGACHAT_VERIFY_SSL_CERTS", "true").lower() == "true"

    @property
    def enabled(self) -> bool:
        return bool(self.credentials)

    async def summarize(self, result: CheckResult) -> str:
        base = self.format_summary_report(result)
        if not self.enabled:
            return base
        context = json.dumps(
            {
                "summary": result.summary,
                "attention_rows": _attention_rows(result.rows),
            },
            ensure_ascii=False,
            default=str,
        )
        accents = await self._ask(
            "Сформируй 2-4 коротких пункта для блока 'Акценты'. "
            "Не повторяй все числа из сводки. Подскажи, на что менеджеру "
            "посмотреть в первую очередь. Не говори, что счет можно оплачивать. "
            f"Результат: {context}"
        )
        return self.format_summary_report(result, accents)

    async def answer(self, result: CheckResult, question: str) -> str:
        if not self.enabled:
            return (
                "GigaChat не настроен. Доступен только итог отчета: "
                + self.fallback_summary(result)
            )
        context = json.dumps(result.to_context(), ensure_ascii=False, default=str)
        return await self._ask(
            f"Ответь на вопрос менеджера по текущей сверке.\n"
            f"Вопрос: {question}\nРезультат сверки: {context}"
        )

    async def hypothesize_manual_rows(self, result: CheckResult) -> str:
        manual_rows = [
            row.to_context()
            for row in result.rows
            if "проверить вручную" in row.status.lower()
            or row.status in {"Штрихкод не найден", "Ошибка данных"}
        ]
        if not manual_rows:
            return "Строк для ручной проверки нет."
        if not self.enabled:
            return "GigaChat не настроен; гипотезы по спорным строкам недоступны."
        context = json.dumps(manual_rows, ensure_ascii=False, default=str)
        return await self._ask(
            "Предложи осторожные гипотезы по спорным строкам. "
            f"Не меняй их статусы.\nСтроки: {context}"
        )

    def fallback_summary(self, result: CheckResult) -> str:
        return self.format_summary_report(result)

    def format_summary_report(self, result: CheckResult, accents: str | None = None) -> str:
        summary = result.summary
        total_problem = (
            summary["Цена отличается"]
            + summary["Количество отличается"]
            + summary["Цена и количество отличаются"]
            + summary["Нет в счете"]
            + summary["Лишнее в счете"]
            + summary["Проверить вручную"]
        )
        risk = _risk_level(summary, total_problem)
        accents_block = _normalize_accents(accents) if accents else _default_accents(summary)
        return (
            "Резюме сверки\n"
            f"Статус: {risk}\n\n"
            "1. Итог по файлам\n"
            f"- Заказ: {summary['Строк в заказе']} строк\n"
            f"- Счет: {summary['Строк в счете']} строк\n"
            f"- Сопоставлено: {summary['Сопоставлено']} строк\n"
            f"- Без расхождений: {summary['ОК']} строк\n\n"
            "2. Что требует внимания\n"
            f"- Цена отличается: {summary['Цена отличается']}\n"
            f"- Количество отличается: {summary['Количество отличается']}\n"
            f"- Цена и количество отличаются: {summary['Цена и количество отличаются']}\n"
            f"- Нет в счете: {summary['Нет в счете']}\n"
            f"- Лишнее в счете: {summary['Лишнее в счете']}\n"
            f"- Проверить вручную: {summary['Проверить вручную']}\n\n"
            "3. Акценты\n"
            f"{accents_block}\n\n"
            "4. Следующий шаг\n"
            "- Откройте Excel-отчет и начните с вкладок "
            "`Проверить вручную`, `Расхождения`, `Нет в счете`.\n"
            "- Можете задать вопрос по этой сверке, например: "
            "`Что проверить сначала?`"
        )

    async def _ask(self, prompt: str) -> str:
        return await asyncio.to_thread(self._ask_sync, prompt)

    def _ask_sync(self, prompt: str) -> str:
        try:
            from gigachat import GigaChat
            from gigachat.models import Chat, Messages, MessagesRole
        except ImportError as exc:
            raise RuntimeError("Пакет gigachat не установлен") from exc

        payload = Chat(
            messages=[
                Messages(role=MessagesRole.SYSTEM, content=SYSTEM_RULES),
                Messages(role=MessagesRole.USER, content=prompt),
            ],
            model=self.model,
        )
        with GigaChat(
            credentials=self.credentials,
            scope=self.scope,
            verify_ssl_certs=self.verify_ssl,
        ) as client:
            response: Any = client.chat(payload)
        return response.choices[0].message.content


def _risk_level(summary: dict[str, int], total_problem: int) -> str:
    if total_problem == 0:
        return "расхождений не найдено"
    if summary["Проверить вручную"] or summary["Нет в счете"] or summary["Лишнее в счете"]:
        return "требуется ручная проверка"
    return "есть расхождения"


def _default_accents(summary: dict[str, int]) -> str:
    points: list[str] = []
    if summary["Проверить вручную"]:
        points.append("- Сначала разберите строки ручной проверки: там не хватает надежных данных для автоматического вывода.")
    if summary["Нет в счете"]:
        points.append("- Проверьте позиции, которые есть в заказе, но отсутствуют в счете.")
    if summary["Лишнее в счете"]:
        points.append("- Проверьте лишние позиции в счете: их нет в заказе.")
    if summary["Цена отличается"] or summary["Цена и количество отличаются"]:
        points.append("- По ценовым расхождениям сравните цену, скидку, НДС и итоговую сумму строки.")
    if summary["Количество отличается"] or summary["Цена и количество отличаются"]:
        points.append("- По количественным расхождениям проверьте единицы измерения и упаковки.")
    if not points:
        points.append("- Критичных расхождений по сводке нет, но финальное решение остается за менеджером.")
    return "\n".join(points[:4])


def _normalize_accents(text: str) -> str:
    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
        and "акценты" not in line.strip().casefold()
    ]
    normalized: list[str] = []
    for line in lines:
        line = line.lstrip("-•0123456789. )")
        if line:
            normalized.append(f"- {line}")
    return "\n".join(normalized[:4]) or "- Откройте отчет и проверьте строки с расхождениями."


def _attention_rows(rows: list[MatchResult], limit: int = 12) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for row in rows:
        if row.status == "ОК":
            continue
        selected.append(
            {
                "status": row.status,
                "name": (row.order or row.invoice).name if (row.order or row.invoice) else "",
                "order_barcode": row.order.barcode if row.order else "",
                "invoice_barcode": row.invoice.barcode if row.invoice else "",
                "order_qty": str(row.order.quantity) if row.order and row.order.quantity is not None else "",
                "invoice_qty": str(row.invoice.quantity) if row.invoice and row.invoice.quantity is not None else "",
                "order_price": str(row.order.price) if row.order and row.order.price is not None else "",
                "invoice_price": str(row.invoice.price) if row.invoice and row.invoice.price is not None else "",
                "comment": row.comment,
            }
        )
        if len(selected) >= limit:
            break
    return selected
