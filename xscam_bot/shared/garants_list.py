"""Динамический список гарантов из БД для /garants и пагинации."""

from __future__ import annotations

from typing import Any

from shared import database as db

ELITE_PAGE_SIZE = 6
TOP_PAGE_SIZE = 6
REGULAR_PAGE_SIZE = 10


def _format_price(value: str | int | None) -> str:
    if value is None or value == "":
        return "0р"
    s = str(value).strip()
    if s.endswith(("р", "₽")):
        return s
    if s.isdigit():
        return f"{s}р"
    return s


def _format_detailed_entry(entry: dict) -> str:
    flag = entry.get("flag", "🇷🇺")
    username = entry.get("username", "")
    proofs = entry.get("proofs", "0+")
    lines = [f"[{flag}]{username} ({proofs})"]
    if entry.get("channel"):
        lines.append(f"📢 Канал: {entry['channel']}")
    lines.append(f"📊 Число пруфов: {proofs}")
    rating = entry.get("rating", "5.0/5")
    lines.append(f"📈 Рейтинг: {rating} ⭐️️")
    if entry.get("tier") == "top":
        if entry.get("deals_count") is not None:
            lines.append(f"🔄 Сделок: {entry['deals_count']}")
    else:
        lines.append(f"💬 Стоимость сделки: {_format_price(entry.get('deal_price'))}")
    handlers = entry.get("handlers") or []
    lines.append("👥 На ручении:")
    for handler in handlers:
        lines.append(f"- {handler}")
    return "\n".join(lines)


def _format_compact_entry(entry: dict) -> str:
    flag = entry.get("flag", "🇷🇺")
    username = entry.get("username", "")
    proofs = entry.get("proofs", "0+")
    lines = [f"[{flag}]{username} ({proofs})"]
    if entry.get("channel"):
        lines.append(f"📢 Канал: {entry['channel']}")
    return "\n".join(lines)


def _chunk(entries: list[dict], size: int) -> list[list[dict]]:
    if not entries:
        return []
    return [entries[i : i + size] for i in range(0, len(entries), size)]


def _build_page_sections(garants: list[dict]) -> list[list[str]]:
    elite = [g for g in garants if g.get("tier") == "elite"]
    top = [g for g in garants if g.get("tier") == "top"]
    regular = [g for g in garants if g.get("tier") not in ("elite", "top")]

    pages: list[list[str]] = []

    if elite:
        for idx, chunk in enumerate(_chunk(elite, ELITE_PAGE_SIZE)):
            blocks: list[str] = []
            if idx == 0:
                blocks.append(f"✅ Элитные гаранты ({len(elite)})")
            blocks.extend(_format_detailed_entry(e) for e in chunk)
            pages.append(blocks)

    if top:
        for idx, chunk in enumerate(_chunk(top, TOP_PAGE_SIZE)):
            blocks = []
            if idx == 0:
                blocks.append(f"🏆 Топ гаранты ({len(top)})")
            blocks.extend(_format_detailed_entry(e) for e in chunk)
            pages.append(blocks)

    if regular:
        for idx, chunk in enumerate(_chunk(regular, REGULAR_PAGE_SIZE)):
            blocks = []
            if idx == 0:
                blocks.append(f"🛡 Гаранты ({len(regular)})")
            blocks.extend(_format_compact_entry(e) for e in chunk)
            pages.append(blocks)

    return pages


def _build_page_keyboard(page: int, total_pages: int) -> dict[str, Any]:
    prev_cb = f"garants_page:{page - 1}" if page > 1 else "noop"
    next_cb = f"garants_page:{page + 1}" if page < total_pages else "noop"
    return {
        "type": "inline",
        "rows": [
            [
                {"text": "◀", "callback_data": prev_cb, "callback_data_decoded": prev_cb},
                {"text": f"{page}/{total_pages}", "callback_data": "noop", "callback_data_decoded": "noop"},
                {"text": "▶", "callback_data": next_cb, "callback_data_decoded": next_cb},
            ],
            [
                {
                    "text": "❓ Кто такой гарант",
                    "url": "https://telegra.ph/Kto-takoj-garant-12-07",
                },
                {
                    "text": "🔎 Поиск гарантов",
                    "callback_data": "garants:search",
                    "callback_data_decoded": "garants:search",
                },
            ],
            [
                {
                    "text": "📂 Другие наши проекты",
                    "url": "https://t.me/Roblox_Chats",
                },
            ],
        ],
    }


def build_all_garants_pages() -> list[dict[str, Any]]:
    garants = db.get_catalog_garants()
    total = len(garants)
    page_sections = _build_page_sections(garants)

    if not page_sections:
        return [{
            "id": 90001,
            "text": "👁‍🗨 Официальные гаранты X-Scam (0):\n\nСписок пуст.",
            "entities": [],
            "media": {"type": "MessageMediaPhoto", "has_photo": True},
            "keyboard": _build_page_keyboard(1, 1),
            "asset_path": None,
        }]

    total_pages = len(page_sections)
    pages: list[dict[str, Any]] = []
    for page_num, blocks in enumerate(page_sections, 1):
        header = f"👁‍🗨 Официальные гаранты X-Scam ({total}):\n\n"
        pages.append({
            "id": 90000 + page_num,
            "text": header + "\n\n".join(blocks),
            "entities": [],
            "media": {"type": "MessageMediaPhoto", "has_photo": True},
            "keyboard": _build_page_keyboard(page_num, total_pages),
            "asset_path": None,
        })
    return pages


def build_garants_page(page: int) -> dict[str, Any]:
    pages = build_all_garants_pages()
    if page < 1:
        page = 1
    if page > len(pages):
        page = len(pages)
    return pages[page - 1]


def total_garants_pages() -> int:
    return max(1, len(build_all_garants_pages()))