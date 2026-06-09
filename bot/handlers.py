from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile, Message

from bot.states import CheckStates
from check_documents import check_documents
from core.catalog import Catalog, CatalogError
from core.file_reader import DocumentReadError
from core.gigachat_client import GigaChatClient
from core.models import CheckResult
from core.paths import CATALOG_PATH, DATA_DIR, PROJECT_ROOT, REPORT_DIR, UPLOAD_DIR


router = Router()
NEW_CHECK_HINT = """Перед загрузкой файлов проверьте их, пожалуйста.

Для более точной сверки оставьте в Excel только строки с товарами.
<b>Обязательно удалить лишние строки, которые не относятся к позициям сверки:</b>

- реквизиты поставщика и покупателя;
- заголовки и служебные блоки;
- итоги, общие суммы и НДС по документу внизу;
- комментарии, подписи

Чем чище таблица, тем меньше строк попадет в ручную проверку."""
current_checks: dict[int, CheckResult] = {}
gigachat = GigaChatClient()
logger = logging.getLogger(__name__)


@router.message(CommandStart())
async def start(message: Message) -> None:
    status = _catalog_status()
    await message.answer(
        "DocCheck Manager Bot сверяет заказ поставщику и счет по штрихкодам.\n"
        "Для новой сверки используйте /new.\n\n"
        f"{status}"
    )


@router.message(Command("help"))
async def help_command(message: Message) -> None:
    await message.answer(
        "1. Подготовьте заказ и счет в формате .xlsx или .xls.\n"
        "2. Запустите /new и отправьте сначала заказ, затем счет.\n"
        "3. Бот сравнит количество, цену и сумму и пришлет Excel-отчет.\n\n"
        "Сопоставление выполняется только через справочник штрихкодов. "
        "Спорные строки требуют решения менеджера."
    )


@router.message(Command("new"))
async def new_check(message: Message, state: FSMContext) -> None:
    if not CATALOG_PATH.exists():
        await message.answer(_catalog_status())
        return
    previous = await state.get_data()
    _cleanup_files(previous.get("order_path"), previous.get("invoice_path"))
    await state.clear()
    await state.set_state(CheckStates.waiting_order)
    await message.answer(NEW_CHECK_HINT, parse_mode="HTML")
    await message.answer("Теперь отправьте Excel-файл заказа.")


@router.message(Command("reset"))
async def reset(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    _cleanup_files(data.get("order_path"), data.get("invoice_path"))
    await state.clear()
    await message.answer("Текущая незавершенная загрузка сброшена.")


@router.message(Command("catalog_status"))
async def catalog_status(message: Message) -> None:
    await message.answer(_catalog_status())


@router.message(Command("history", "update_catalog"))
async def future_command(message: Message) -> None:
    await message.answer("Эта команда не входит в MVP v1.")


@router.message(CheckStates.waiting_order, F.document)
async def receive_order(message: Message, state: FSMContext) -> None:
    path = await _download_excel(message)
    if path is None:
        return
    await state.update_data(order_path=str(path))
    await state.set_state(CheckStates.waiting_invoice)
    await message.answer("Заказ получен. Теперь отправьте Excel-файл счета.")


@router.message(CheckStates.waiting_invoice, F.document)
async def receive_invoice(message: Message, state: FSMContext) -> None:
    invoice_path = await _download_excel(message)
    if invoice_path is None:
        return
    data = await state.get_data()
    order_path = data.get("order_path")
    if not order_path:
        await state.clear()
        await message.answer("Файл заказа потерян. Запустите /new заново.")
        return
    await message.answer("Файлы получены. Выполняю сверку.")
    report_path = REPORT_DIR / f"doccheck_report_{message.from_user.id}_{uuid4().hex}.xlsx"
    try:
        result, report = await asyncio.to_thread(
            check_documents,
            order_path,
            str(invoice_path),
            str(CATALOG_PATH),
            str(report_path),
        )
    except (DocumentReadError, CatalogError, ValueError) as exc:
        _cleanup_files(order_path, invoice_path, report_path)
        await message.answer(str(exc))
        return
    except Exception:
        _cleanup_files(order_path, invoice_path, report_path)
        await message.answer("Не удалось выполнить сверку из-за внутренней ошибки.")
        return
    finally:
        await state.clear()

    current_checks[message.from_user.id] = result
    await message.answer_document(FSInputFile(report), caption="Сверка завершена.")
    try:
        summary = await gigachat.summarize(result)
    except Exception as exc:
        logger.exception("GigaChat summary failed")
        summary = gigachat.fallback_summary(result)
        summary += f"\n\nGigaChat временно недоступен: {type(exc).__name__}."
    await message.answer(summary)
    _cleanup_files(order_path, invoice_path, report)


@router.message(CheckStates.waiting_order)
async def order_expected(message: Message) -> None:
    await message.answer("Ожидается Excel-файл заказа.")


@router.message(CheckStates.waiting_invoice)
async def invoice_expected(message: Message) -> None:
    await message.answer("Ожидается Excel-файл счета.")


@router.message(F.text)
async def answer_question(message: Message) -> None:
    result = current_checks.get(message.from_user.id)
    if result is None:
        await message.answer("Сначала выполните сверку командой /new.")
        return
    try:
        answer = await gigachat.answer(result, message.text)
    except Exception as exc:
        logger.exception("GigaChat answer failed")
        answer = (
            "Не удалось получить ответ GigaChat. Excel-отчет остается доступен.\n"
            f"Техническая причина: {type(exc).__name__}."
        )
    await message.answer(answer)


async def _download_excel(message: Message) -> Path | None:
    document = message.document
    suffix = Path(document.file_name or "").suffix.lower()
    if suffix not in {".xlsx", ".xls"}:
        await message.answer("Поддерживаются только файлы .xlsx и .xls.")
        return None
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = Path(document.file_name or f"document{suffix}").name
    destination = UPLOAD_DIR / f"{message.from_user.id}_{uuid4().hex}_{safe_name}"
    await message.bot.download(document, destination=destination)
    return destination


def _catalog_status() -> str:
    try:
        catalog = Catalog.load(CATALOG_PATH)
    except CatalogError:
        return (
            "Справочник номенклатуры не найден.\n"
            f"Корень проекта: {PROJECT_ROOT}\n"
            f"Путь поиска: {CATALOG_PATH}\n"
            f"Папка data существует: {'да' if DATA_DIR.exists() else 'нет'}\n"
            f"Файлы в data: {_data_dir_listing()}"
        )
    modified = datetime.fromtimestamp(CATALOG_PATH.stat().st_mtime).strftime(
        "%Y-%m-%d %H:%M"
    )
    return (
        f"Справочник найден. Штрихкодов: {catalog.barcode_count}. "
        f"Изменен: {modified}."
    )


def _data_dir_listing() -> str:
    if not DATA_DIR.exists():
        return "папка не найдена"
    files = sorted(path.name for path in DATA_DIR.iterdir())
    return ", ".join(files) if files else "папка пустая"


def _cleanup_files(*paths: str | Path | None) -> None:
    for value in paths:
        if not value:
            continue
        path = Path(value)
        if path.is_file() and path.parent in {UPLOAD_DIR, REPORT_DIR}:
            path.unlink(missing_ok=True)
