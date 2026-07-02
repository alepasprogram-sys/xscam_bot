"""Шаблоны и индивидуальные фото профилей (папка «взгляд» + загрузка из админки)."""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from shared.assets import ASSETS_DIR, get_photo, get_video


def photo_key_for_garant(entry: dict) -> str:
    tier = entry.get("tier", "regular")
    if tier == "elite":
        return "garant_elite"
    if tier == "top":
        return "garant_top"
    return "garant_regular"

CUSTOM_DIR = ASSETS_DIR / "custom_profiles"

PROFILE_TYPES = {
    "scammer": ("Мошенник", "user_scammer"),
    "suspicious": ("Подозрительный", "user_suspicious"),
    "garant": ("Гарант", "garant_regular"),
    "clean": ("Обычный пользователь", "user_verified"),
}


def ensure_custom_dir() -> Path:
    CUSTOM_DIR.mkdir(parents=True, exist_ok=True)
    return CUSTOM_DIR


def template_key_for_group(group: str, entry: dict | None = None) -> str:
    if group == "garant" and entry:
        return photo_key_for_garant(entry)
    return PROFILE_TYPES.get(group, PROFILE_TYPES["clean"])[1]


def save_custom_photo(data: bytes, *, kind: str, stem: str) -> str:
    """Сохранить фото, вернуть имя файла (относительно custom_profiles/)."""
    ensure_custom_dir()
    safe = re.sub(r"[^\w.-]", "_", stem.lower().lstrip("@"))[:48] or "user"
    name = f"{kind}_{safe}_{uuid.uuid4().hex[:8]}.jpg"
    path = CUSTOM_DIR / name
    path.write_bytes(data)
    return name


def resolve_profile_photo(
    *,
    group: str,
    entry: dict | None = None,
) -> Path | None:
    if entry and entry.get("photo_file"):
        custom = CUSTOM_DIR / entry["photo_file"]
        if custom.is_file():
            return custom
    key = template_key_for_group(group, entry)
    return get_photo(key)


def resolve_profile_banner(
    *,
    group: str,
    entry: dict | None = None,
) -> Path | None:
    if group != "garant" or not entry:
        return None
    if entry.get("tier") == "top":
        return get_video("garant_top_extra")
    return None


def template_preview_path(profile_type: str) -> Path | None:
    key = PROFILE_TYPES.get(profile_type, PROFILE_TYPES["clean"])[1]
    if profile_type == "garant":
        for k in ("garant_regular", "garant_elite", "garant_top"):
            p = get_photo(k)
            if p:
                return p
    return get_photo(key)