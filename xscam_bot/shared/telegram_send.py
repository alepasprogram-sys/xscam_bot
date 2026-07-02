import asyncio
import logging

import aiohttp

from shared.config import BOT_TOKEN

logger = logging.getLogger(__name__)


async def send_main_bot_message(telegram_id: int, text: str) -> bool:
    if not BOT_TOKEN:
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json={
                    "chat_id": telegram_id,
                    "text": text[:4096],
                    "parse_mode": "HTML",
                },
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json()
                return bool(data.get("ok"))
    except Exception as exc:
        logger.warning("send_main_bot_message %s: %s", telegram_id, exc)
        return False


async def broadcast_async(user_ids: list[int], text: str) -> tuple[int, int]:
    sent = failed = 0
    for uid in user_ids:
        if await send_main_bot_message(uid, text):
            sent += 1
        else:
            failed += 1
        await asyncio.sleep(0.05)
    return sent, failed