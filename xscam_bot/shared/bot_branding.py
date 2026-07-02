"""Подмена юзернейма официального бота на наш."""

from __future__ import annotations

from shared.config import BOT_USERNAME

_REPLACEMENTS = (
    ("@Xscam_bot", BOT_USERNAME),
    ("@xscam_bot", BOT_USERNAME),
    ("https://t.me/Xscam_bot", f"https://t.me/{BOT_USERNAME.lstrip('@')}"),
    ("https://t.me/xscam_bot", f"https://t.me/{BOT_USERNAME.lstrip('@')}"),
    ("tg://resolve?domain=Xscam_bot", f"tg://resolve?domain={BOT_USERNAME.lstrip('@')}"),
    ("tg://resolve?domain=xscam_bot", f"tg://resolve?domain={BOT_USERNAME.lstrip('@')}"),
)


def apply_bot_branding(text: str | None) -> str:
    if not text:
        return text or ""
    result = text
    for old, new in _REPLACEMENTS:
        result = result.replace(old, new)
    return result