"""Разрешение Telegram ID по username и известным источникам."""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

from shared import database as db

logger = logging.getLogger(__name__)


async def resolve_target_id(
    bot: Bot | None,
    username: str | None,
    user_id: int | None = None,
) -> int | None:
    found = db.lookup_target_id(username, user_id)
    if found is not None:
        return found

    uname = (username or "").lstrip("@").lower()
    if not uname or not bot:
        return None

    try:
        chat = await bot.get_chat(f"@{uname}")
    except TelegramBadRequest:
        return None
    except Exception as exc:
        logger.debug("get_chat @%s: %s", uname, exc)
        return None

    if chat.id:
        return int(chat.id)
    return None