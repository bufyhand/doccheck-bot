from __future__ import annotations

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramNetworkError
from aiogram.types import BotCommand
from dotenv import load_dotenv


async def main() -> None:
    load_dotenv()
    from bot.handlers import router

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("Переменная TELEGRAM_BOT_TOKEN не задана")
    logging.basicConfig(level=logging.INFO)
    proxy = os.getenv("TELEGRAM_PROXY") or None
    bot = Bot(token=token, session=AiohttpSession(proxy=proxy))
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    try:
        await bot.set_my_commands(
            [
                BotCommand(command="start", description="О боте"),
                BotCommand(command="help", description="Инструкция"),
                BotCommand(command="new", description="Новая сверка"),
                BotCommand(command="reset", description="Сбросить загрузку"),
                BotCommand(command="catalog_status", description="Статус справочника"),
            ]
        )
        await dispatcher.start_polling(bot)
    except TelegramNetworkError as exc:
        logging.error(
            "Не удалось подключиться к api.telegram.org. "
            "Проверьте сеть или задайте TELEGRAM_PROXY в .env: %s",
            exc,
        )
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
