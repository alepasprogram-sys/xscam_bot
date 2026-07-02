"""Профиль пользователя — текст как в bot_data, данные из БД."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from aiogram.types import FSInputFile, InlineKeyboardMarkup, Message

from runtime import keyboard_from_dict, runtime

logger = logging.getLogger(__name__)
from shared import database as db
from shared.parsers import format_target
from shared.profile_photos import resolve_profile_banner, resolve_profile_photo
from shared.bot_branding import apply_bot_branding
from shared.config import BOT_USERNAME
from shared.premium_emojis import (
    PROFILE_CLEAN_USER,
    PROFILE_DATE,
    PROFILE_DB_CHECK,
    PROFILE_ID,
    PROFILE_NAME,
    PROFILE_ROLE,
    PROFILE_ROLE_ARROW,
    PROFILE_SEARCHED,
    PROFILE_VERIFIED,
    tg,
)
from shared.user_resolver import resolve_target_id

BOT_CHECK_LABEL = BOT_USERNAME
STARS = "⭐️"


def _rating_stars(rating: str | int | float | None) -> str:
    raw = str(rating or "5.0/5").strip()
    try:
        head = raw.split("/")[0].strip().replace(",", ".")
        count = round(float(head))
    except (TypeError, ValueError):
        count = 5
    count = max(0, min(5, count))
    return STARS * count


def _search_label(count: int) -> str:
    n = abs(int(count)) % 100
    if 11 <= n <= 14:
        suffix = "раз"
    else:
        rem = n % 10
        if rem == 1:
            suffix = "раз"
        elif 2 <= rem <= 4:
            suffix = "раза"
        else:
            suffix = "раз"
    return f"{count} {suffix}"


def _id_line_html(user_id: int | None) -> str:
    """Скобки снаружи — копируется только число внутри <code>."""
    icon = tg(PROFILE_ID, "🪪")
    if user_id is not None:
        return f"{icon}id: [<code>{user_id}</code>]"
    return f"{icon}id: [<code>—</code>]"


def _date_str() -> str:
    return datetime.now(timezone.utc).strftime("%d.%m.%Y")


def _norm_price(value: str | int | None) -> str:
    raw = str(value or "0").strip()
    for suffix in ("₽", "р", "p"):
        if raw.endswith(suffix):
            return raw[: -len(suffix)] + "р"
    if raw.replace(".", "", 1).isdigit():
        return f"{raw}р"
    return raw


def _handlers_list(entry: dict) -> list[str]:
    handlers = entry.get("handlers")
    if isinstance(handlers, list):
        return [h for h in handlers if h]
    single = entry.get("handler")
    return [single] if single else []


def _resolve_group(
    username: str | None,
    user_id: int | None,
) -> tuple[str, dict | None]:
    garant = db.find_catalog_garant(username)
    if garant:
        return "garant", garant
    scammer = db.find_blacklist(username, user_id)
    if scammer:
        return "scammer", scammer
    suspicious = db.find_suspicious(username, user_id)
    if suspicious:
        return "suspicious", suspicious
    return "clean", None


def _entry_stored_id(entry: dict | None) -> int | None:
    if not entry:
        return None
    for key in ("target_id", "telegram_id", "user_id"):
        raw = entry.get(key)
        if raw is None:
            continue
        try:
            return int(raw)
        except (TypeError, ValueError):
            continue
    return None


def _resolve_display_user_id(
    username: str | None,
    user_id: int | None,
    group: str,
    entry: dict | None,
) -> int | None:
    if user_id is not None:
        return int(user_id)
    stored = _entry_stored_id(entry)
    if stored is not None:
        return stored
    return db.lookup_target_id(username, user_id)


def _stats_username(
    username: str | None,
    user_id: int | None,
    group: str,
    entry: dict | None,
) -> tuple[str | None, int | None]:
    if group == "garant" and entry:
        uname = (entry.get("username") or "").lstrip("@").lower()
        return uname or username, user_id
    return username, user_id


def _bump_search_stats(
    *,
    username: str | None,
    user_id: int | None,
    checker_id: int,
    log_check: bool,
    found_in_db: bool,
) -> int:
    if log_check:
        db.log_check(checker_id, username, user_id, found_in_db)
    else:
        db.increment_target_search(username, user_id)
    return db.get_target_search_count(username, user_id)


def _count_scam_reasons(reason: str) -> int:
    if not reason:
        return 0
    return sum(1 for line in reason.splitlines() if line.strip())


def _build_garant_lines(entry: dict) -> list[str]:
    tier = entry.get("tier", "elite")
    flag = entry.get("flag", "🇷🇺")
    role = entry.get("role_label", "Гарант")
    rating = entry.get("rating", "5.0/5")
    votes = int(entry.get("rating_votes") or 0)
    stars = _rating_stars(rating)
    lines = ["📎Роль пользователя..."]

    if tier == "regular":
        lines.append(f"🛡 {role} [{flag}]")
        if entry.get("senior_admin"):
            lines.append("👑 Старший Админ")
        if entry.get("channel"):
            lines.append(f"📢 Канал гаранта: {entry['channel']}")
        vote_part = f" ({votes})" if votes else ""
        lines.append(f"📈 Рейтинг: {rating}{vote_part} {stars}")
        if entry.get("scammers_added") is not None:
            lines.append(f"➕ Добавлено скамеров: {entry['scammers_added']}")
        warns = (entry.get("warns") or "").strip()
        if warns:
            lines.append(f"⚠️ Варны: {warns}")
        return lines

    lines.append(f"🛡 {role} {flag}")
    if entry.get("channel"):
        lines.append(f"📢 Канал гаранта: {entry['channel']}")
    vote_part = f" ({votes})" if votes else ""
    lines.append(f"📈 Рейтинг: {rating}{vote_part} {stars}")
    if tier == "top" and entry.get("deals_count") is not None:
        lines.append(f"🔄 Сделок: {entry['deals_count']}")
    else:
        lines.append(f"💬 Стоимость сделки: {_norm_price(entry.get('deal_price'))}")
    handlers = _handlers_list(entry)
    if handlers:
        lines.append("👥 На ручении:")
        for handler in handlers:
            lines.append(f"- {handler}")
    warns = (entry.get("warns") or "").strip()
    if warns:
        lines.append(f"⚠️ Варны: {warns}")
    return lines


def _profile_template() -> dict[str, Any] | None:
    responses = runtime.get_responses("command", "/me")
    return responses[0] if responses else None


def _apply_profile_placeholders(
    template: str,
    *,
    display_name: str,
    display_id: int | None,
    search_label: str,
    date_str: str,
    reason: str = "",
) -> str:
    id_value = str(display_id) if display_id is not None else "—"
    replacements = {
        "{username}": display_name,
        "{id}": id_value,
        "{search}": search_label,
        "{date}": date_str,
        "{reason}": reason,
    }
    text = template
    replacements["{bot}"] = BOT_CHECK_LABEL
    for key, value in replacements.items():
        text = text.replace(key, value)
    return apply_bot_branding(text)


def _profile_keyboard() -> InlineKeyboardMarkup | None:
    template = _profile_template()
    if not template:
        return None
    return keyboard_from_dict(template.get("keyboard"))


def build_profile_html(
    *,
    username: str | None,
    user_id: int | None,
    checker_id: int = 0,
    log_check: bool = True,
) -> str:
    group, entry = _resolve_group(username, user_id)
    display_id = _resolve_display_user_id(username, user_id, group, entry)
    stat_user, stat_id = _stats_username(username, display_id, group, entry)

    search_count = _bump_search_stats(
        username=stat_user,
        user_id=stat_id,
        checker_id=checker_id,
        log_check=log_check,
        found_in_db=group in ("scammer", "suspicious"),
    )
    date_str = _date_str()

    display_name = (
        entry.get("username") if group == "garant" and entry else format_target(username, display_id)
    )
    search_label = _search_label(search_count)
    if entry and (entry.get("profile_text") or "").strip():
        reason = (entry.get("reason") or entry.get("channel") or "").strip()
        return _apply_profile_placeholders(
            entry["profile_text"].strip(),
            display_name=display_name,
            display_id=display_id,
            search_label=search_label,
            date_str=date_str,
            reason=reason,
        )

    lines = [
        f"{tg(PROFILE_NAME, '👤')}Имя: {display_name}  ",
        _id_line_html(display_id),
        "",
        f"{tg(PROFILE_DB_CHECK, '⚙')}Проверка в базе данных...",
        "",
    ]

    if group == "garant" and entry:
        lines.extend(_build_garant_lines(entry))
    elif group == "scammer" and entry:
        count = entry.get("scam_count") or _count_scam_reasons(entry.get("reason", ""))
        lines.append(f"{tg(PROFILE_ROLE, '📎')}Роль пользователя... Мошенник")
        lines.append(f"📁 Количество скамов: {count}")
        reason = (entry.get("reason") or "").strip()
        if reason:
            lines.append(reason)
    elif group == "suspicious" and entry:
        count = entry.get("scam_count") or 0
        lines.append(f"{tg(PROFILE_ROLE, '📎')}Роль пользователя...")
        lines.append("⚠️ Подозрительный")
        lines.append(f"📁 Количество скамов: {count}")
        reason = (entry.get("reason") or "").strip()
        if reason:
            lines.append(reason)
    else:
        lines.append(f"{tg(PROFILE_ROLE, '📎')}Роль пользователя...")
        lines.append(
            f"{tg(PROFILE_ROLE_ARROW, '➡️')}Пользователя нет в базе "
            f"{tg(PROFILE_CLEAN_USER, '👤')}"
        )

    lines.extend([
        "",
        f"{tg(PROFILE_SEARCHED, '🔎')}Пользователя искали: {search_label}",
        f"{tg(PROFILE_VERIFIED, '✅')}Проверено в {BOT_CHECK_LABEL}",
        f"{tg(PROFILE_DATE, '🗓')}Дата проверки [{date_str}]",
    ])
    return apply_bot_branding("\n".join(lines))


def username_from_garant(entry: dict) -> str | None:
    raw = entry.get("username") or ""
    return raw.lstrip("@").lower() or None


def entry_user_id(entry: dict | None) -> int | None:
    return _entry_stored_id(entry)


async def send_profile(
    message: Message,
    *,
    username: str | None = None,
    user_id: int | None = None,
    log_check: bool = True,
) -> None:
    checker_id = message.from_user.id if message.from_user else 0
    if username:
        username = username.lstrip("@").lower()

    resolved_id = await resolve_target_id(message.bot, username, user_id)
    if resolved_id is not None:
        user_id = resolved_id
    if user_id is not None:
        db.remember_target_id(username, user_id)
    try:
        group, entry = _resolve_group(username, user_id)
        html = build_profile_html(
            username=username,
            user_id=user_id,
            checker_id=checker_id,
            log_check=log_check,
        )
        kb = _profile_keyboard()
        photo = resolve_profile_photo(group=group, entry=entry)
        banner = resolve_profile_banner(group=group, entry=entry)
    except Exception as exc:
        logger.exception("Не удалось собрать профиль: %s", exc)
        await message.answer("Не удалось показать профиль. Попробуйте ещё раз.")
        return

    try:
        if photo:
            await message.answer_photo(
                FSInputFile(photo),
                caption=html,
                parse_mode="HTML",
                reply_markup=kb,
            )
        else:
            await message.answer(html, parse_mode="HTML", reply_markup=kb)

        if banner:
            if banner.suffix.lower() in {".mov", ".mp4", ".webm"}:
                await message.answer_video(FSInputFile(banner))
            else:
                await message.answer_photo(FSInputFile(banner))
    except Exception as exc:
        logger.warning("Отправка профиля с фото не удалась, шлём текст: %s", exc)
        await message.answer(html, parse_mode="HTML", reply_markup=kb)