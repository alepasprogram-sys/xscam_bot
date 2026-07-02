"""
Бот @Xscamss_bot
Сгенерировано автоматически программой Telegram Bot Cloner.
"""

import asyncio
import logging
import os
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.types import BotCommand
from dotenv import load_dotenv

from admin.handlers import router as admin_router
from handlers import router
from shared.database import init_db
from shared.import_original import auto_import_if_present, seed_catalog_from_config
from shared.proxy_utils import default_proxy, resolve_proxy

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent

COMMAND_DESCRIPTIONS = {
    "start": "Запуск бота",
    "me": "Мой профиль",
    "check": "Проверить на скам",
    "info": "О проекте",
    "help": "Список команд",
    "garants": "Список гарантов",
    "admins": "Список админов",
    "sponsors": "Спонсоры",
    "start_deal": "Сделка через гаранта",
    "cancel": "Отмена",
    "id": "Мой ID",
}


async def setup_commands(bot: Bot) -> None:
    commands = [
        BotCommand(command=name, description=desc)
        for name, desc in COMMAND_DESCRIPTIONS.items()
    ]
    try:
        await bot.set_my_commands(commands)
    except Exception as exc:
        logger.warning("Не удалось установить команды: %s", exc)


async def setup_bot_profile(bot: Bot) -> None:
    description = (
        "👁‍🗨Новости: @Xscam_Community\n\n"
        "🎬Слить Скамера: https://t.me/+ywX887f10lU4NTY6"
    )
    try:
        await bot.set_my_description(description=description)
    except Exception as exc:
        logger.warning("Не удалось установить описание: %s", exc)

    try:
        await bot.set_my_short_description(short_description="X-Scam | Бот для проверки на скам")
    except Exception as exc:
        logger.warning("Не удалось установить краткое описание: %s", exc)


def _create_bot(token: str) -> Bot:
    proxy = resolve_proxy()
    configured = os.getenv("PROXY", default_proxy()).strip()
    kwargs: dict = {
        "token": token,
        "default": DefaultBotProperties(parse_mode=ParseMode.HTML),
    }
    if proxy:
        kwargs["session"] = AiohttpSession(proxy=proxy)
        logger.info("Прокси: %s", proxy)
    elif configured:
        logger.warning(
            "Прокси %s недоступен — подключение напрямую. Включите Happ VPN + Allow LAN.",
            configured,
        )
    return Bot(**kwargs)


async def main() -> None:
    token = os.getenv("BOT_TOKEN")
    if not token or token == "YOUR_BOT_TOKEN_HERE":
        raise SystemExit("Укажите BOT_TOKEN в файле .env (получите у @BotFather)")

    init_db()
    seed_catalog_from_config()
    imported = auto_import_if_present()
    if imported:
        bl = imported.get("blacklist", {})
        logger.info(
            "Импорт из оригинала: скамеров +%s",
            bl.get("added", 0),
        )

    main_bot = _create_bot(token)
    main_dp = Dispatcher()
    main_dp.include_router(router)

    await setup_commands(main_bot)
    await setup_bot_profile(main_bot)

    tasks = [main_dp.start_polling(main_bot)]
    log_parts = ["основной бот"]

    admin_token = os.getenv("ADMIN_BOT_TOKEN", "").strip()
    if admin_token and admin_token != "YOUR_ADMIN_BOT_TOKEN_HERE":
        admin_bot = _create_bot(admin_token)
        admin_dp = Dispatcher()
        admin_dp.include_router(admin_router)
        tasks.append(admin_dp.start_polling(admin_bot))
        log_parts.append("админ-бот")

    logger.info("Папка бота: %s", BASE_DIR)
    logger.info("Запущено: %s", " + ".join(log_parts))
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())