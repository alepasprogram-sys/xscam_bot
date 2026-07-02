"""Управление записями баз (мошенник / подозрительный / гарант) для админки."""

from __future__ import annotations

from shared import database as db

ENTRY_TYPES: dict[str, tuple[str, str, str]] = {
    "scammer": ("🚨 Мошенник", "blacklist", "scammer"),
    "suspicious": ("⚠️ Подозрительный", "suspicious", "suspicious"),
    "garant": ("🛡 Гарант", "catalog_garants", "garant"),
}

GARANT_SUBTYPES: dict[str, tuple[str, str]] = {
    "garant_elite": ("👑 Элитные гаранты", "elite"),
    "garant_top": ("🏆 Топ гаранты", "top"),
    "garant_regular": ("🛡 Обычные гаранты", "regular"),
}

GARANT_TIER_DEFAULTS: dict[str, dict[str, str]] = {
    "elite": {
        "tier": "elite",
        "subgroup": "Элитные гаранты",
        "role_label": "Элитный гарант",
    },
    "top": {
        "tier": "top",
        "subgroup": "Топ гаранты",
        "role_label": "Топ гарант",
    },
    "regular": {
        "tier": "regular",
        "subgroup": "Гаранты",
        "role_label": "Гарант",
    },
}


def resolve_list_type(list_type: str) -> tuple[str, str | None]:
    """Вернуть (базовый тип, фильтр тира) для списка в редакторе."""
    if list_type in GARANT_SUBTYPES:
        return "garant", GARANT_SUBTYPES[list_type][1]
    return list_type, None


def garant_list_type_for_entry(entry: dict) -> str:
    tier = entry.get("tier", "elite")
    for key, (_, t) in GARANT_SUBTYPES.items():
        if t == tier:
            return key
    return "garant_regular"


def entry_type_label(entry_type: str) -> str:
    return ENTRY_TYPES.get(entry_type, ("?", "", ""))[0]


def _entry_target_label(entry: dict, entry_type: str) -> str:
    if entry_type == "garant":
        return entry.get("username") or "—"
    from shared.parsers import format_target

    return format_target(entry.get("target_username"), entry.get("target_id"))


def get_entry(entry_type: str, entry_id: int) -> dict | None:
    return db.get_entry_by_type(entry_type, entry_id)


def list_entries(entry_type: str, *, limit: int = 5, offset: int = 0) -> list[dict]:
    base_type, tier = resolve_list_type(entry_type)
    if base_type == "garant" and tier:
        return db.list_garants_by_tier(tier, limit=limit, offset=offset)
    return db.list_entries_by_type(base_type, limit=limit, offset=offset)


def count_entries(entry_type: str) -> int:
    base_type, tier = resolve_list_type(entry_type)
    if base_type == "garant" and tier:
        return db.count_garants_by_tier(tier)
    return db.count_entries_by_type(base_type)


def find_entry_anywhere(username: str | None = None, user_id: int | None = None) -> list[dict]:
    found: list[dict] = []
    bl = db.find_blacklist(username, user_id)
    if bl:
        found.append({"entry_type": "scammer", "entry": bl})
    sus = db.find_suspicious(username, user_id)
    if sus:
        found.append({"entry_type": "suspicious", "entry": sus})
    gr = db.find_catalog_garant(username) if username else None
    if gr:
        found.append({"entry_type": "garant", "entry": gr})
    return found


def update_photo(entry_type: str, entry_id: int, photo_file: str | None) -> bool:
    return db.update_entry_field(entry_type, entry_id, photo_file=photo_file)


def update_profile_text(entry_type: str, entry_id: int, text: str | None) -> bool:
    return db.update_entry_field(entry_type, entry_id, profile_text=text)


def update_reason(entry_type: str, entry_id: int, reason: str) -> bool:
    if entry_type == "garant":
        return db.update_entry_field(entry_type, entry_id, channel=reason or None)
    return db.update_entry_field(entry_type, entry_id, reason=reason)


def update_garant_fields(entry_id: int, **fields) -> bool:
    return db.update_entry_field("garant", entry_id, **fields)


def delete_entry(entry_type: str, entry_id: int) -> bool:
    return db.delete_entry_by_type(entry_type, entry_id)


def move_entry(entry_type: str, entry_id: int, new_type: str, *, admin_id: int = 0) -> bool:
    if entry_type not in ENTRY_TYPES or new_type not in ENTRY_TYPES:
        return False
    if entry_type == new_type:
        return True
    entry = get_entry(entry_type, entry_id)
    if not entry:
        return False

    username, user_id, reason, photo, profile_text = _extract_payload(entry, entry_type)
    if not delete_entry(entry_type, entry_id):
        return False

    if new_type == "scammer":
        return db.add_blacklist(
            target_username=username,
            target_id=user_id,
            reason=reason or "перенесено из другой базы",
            added_by=admin_id,
            photo_file=photo,
            profile_text=profile_text,
        )
    if new_type == "suspicious":
        return db.add_suspicious(
            target_username=username,
            target_id=user_id,
            reason=reason,
            added_by=admin_id,
            photo_file=photo,
            profile_text=profile_text,
        )
    if new_type == "garant":
        uname = username or (f"id{user_id}" if user_id else "")
        tier_defaults = GARANT_TIER_DEFAULTS["regular"]
        if entry_type == "garant":
            tier_defaults = GARANT_TIER_DEFAULTS.get(
                entry.get("tier", "regular"),
                GARANT_TIER_DEFAULTS["regular"],
            )
        return db.append_catalog_garant({
            "username": uname,
            "channel": reason or None,
            "photo_file": photo,
            "profile_text": profile_text,
            "telegram_id": user_id,
            **tier_defaults,
        })
    return False


def remove_from_all_databases(username: str | None, user_id: int | None) -> int:
    removed = 0
    if db.remove_blacklist(username, user_id):
        removed += 1
    if db.remove_suspicious(username, user_id):
        removed += 1
    if username:
        entry = db.find_catalog_garant(username)
        if entry and entry.get("id") and db.delete_entry_by_type("garant", int(entry["id"])):
            removed += 1
    return removed


def _extract_payload(entry: dict, entry_type: str) -> tuple:
    if entry_type == "garant":
        username = (entry.get("username") or "").lstrip("@").lower() or None
        user_id = entry.get("telegram_id") or entry.get("target_id")
        reason = entry.get("channel") or ""
        photo = entry.get("photo_file")
        profile_text = entry.get("profile_text")
    else:
        username = entry.get("target_username")
        user_id = entry.get("target_id")
        reason = entry.get("reason") or ""
        photo = entry.get("photo_file")
        profile_text = entry.get("profile_text")
    return username, user_id, reason, photo, profile_text


def format_entry_summary(entry_type: str, entry: dict) -> str:
    target = _entry_target_label(entry, entry_type)
    label = entry_type_label(entry_type)
    photo = "своё фото" if entry.get("photo_file") else "шаблон"
    custom = "да" if (entry.get("profile_text") or "").strip() else "авто"
    lines = [f"<b>{label}</b> #{entry.get('id', '?')} {target}", f"Фото: {photo}", f"Текст: {custom}"]
    if entry_type == "garant":
        tier = entry.get("tier", "elite")
        lines.append(f"Тир: {tier}")
        if entry.get("role_label"):
            lines.append(f"Роль: {entry['role_label']}")
        if entry.get("channel"):
            lines.append(f"Канал: {entry['channel']}")
        if entry.get("proofs"):
            lines.append(f"Пруфы: {entry['proofs']}")
        if entry.get("rating"):
            votes = entry.get("rating_votes") or 0
            vote_part = f" ({votes})" if votes else ""
            lines.append(f"Рейтинг: {entry['rating']}{vote_part}")
        if tier == "top" and entry.get("deals_count") is not None:
            lines.append(f"Сделок: {entry['deals_count']}")
        elif entry.get("deal_price") is not None:
            lines.append(f"Стоимость: {entry['deal_price']}")
        handlers = entry.get("handlers") or []
        if handlers:
            lines.append(f"Ручения: {', '.join(handlers[:3])}")
    else:
        reason = (entry.get("reason") or "—")[:200]
        lines.append(f"Причина: {reason}")
    return "\n".join(lines)