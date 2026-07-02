"""Проверка доступности премиум-эмодзи для бота."""

from __future__ import annotations

import json
from pathlib import Path

from aiogram import Bot

BASE_DIR = Path(__file__).resolve().parent.parent
CUSTOM_EMOJIS = BASE_DIR / "custom_emojis.json"
OUT_JSON = BASE_DIR / "emojis" / "проверка_id.json"


def load_emoji_ids() -> tuple[dict, list[str]]:
    custom = json.loads(CUSTOM_EMOJIS.read_text(encoding="utf-8"))
    ids = sorted({str(v["document_id"]) for v in custom.values()})
    return custom, ids


async def check_emoji_availability(bot: Bot) -> tuple[list[dict], str]:
    custom, ids = load_emoji_ids()
    stickers = await bot.get_custom_emoji_stickers(custom_emoji_ids=ids, request_timeout=90)
    available = {s.custom_emoji_id for s in stickers if s.custom_emoji_id}

    rows: list[dict] = []
    ok_count = 0
    for doc_id in ids:
        entry = custom.get(doc_id, {})
        works = doc_id in available
        if works:
            ok_count += 1
        rows.append(
            {
                "document_id": doc_id,
                "available": works,
                "name": entry.get("name", ""),
                "title": entry.get("title", ""),
                "alt": entry.get("alt", ""),
            }
        )

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    failed = [r for r in rows if not r["available"]]
    lines = [
        f"<b>Проверка премиум-эмодзи</b>",
        f"Всего ID: {len(ids)}",
        f"Доступны: {ok_count}",
        f"Недоступны: {len(failed)}",
    ]
    if failed:
        lines.append("\n<b>Нужно заменить:</b>")
        for r in failed[:15]:
            label = r["name"] or r["title"] or r["alt"] or "?"
            lines.append(f"• <code>{r['document_id']}</code> — {label}")
        if len(failed) > 15:
            lines.append(f"… и ещё {len(failed) - 15}")
    else:
        lines.append("\n✅ Все эмодзи доступны боту.")

    lines.append(f"\nОтчёт: <code>{OUT_JSON.name}</code>")
    return rows, "\n".join(lines)