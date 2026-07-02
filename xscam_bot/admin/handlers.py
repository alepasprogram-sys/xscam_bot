"""Админ-панель X-Scam (порт с xscam-bott на aiogram)."""

from __future__ import annotations

import logging
import os
from io import BytesIO
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from admin.entry_editor import (
    handle_find_query,
    handle_photo_upload,
    handle_text_flow,
    process_entry_callback,
    show_entries_menu,
)
from admin.keyboards import (
    add_mode_menu,
    add_type_menu,
    admin_menu,
    blacklist_entry_actions,
    broadcast_confirm,
    complaint_actions,
    page_nav,
    template_preview_menu,
)
from shared import database as db
from shared.config import ADMIN_PASSWORD, BASE_DIR
from shared.emoji_check import check_emoji_availability
from shared.message_entities import message_to_storage_html
from shared.import_original import import_all_from_sqlite
from shared.parsers import format_target, parse_target
from shared.entry_store import GARANT_TIER_DEFAULTS
from shared.profile_photos import PROFILE_TYPES, save_custom_photo, template_preview_path
from shared.telegram_send import broadcast_async

logger = logging.getLogger(__name__)
router = Router()

PAGE_SIZE = 5
_sessions: dict[int, dict] = {}


def _session(user_id: int) -> dict:
    return _sessions.setdefault(user_id, {})


def _is_auth(user_id: int) -> bool:
    return bool(_session(user_id).get("admin_auth"))


def _add_type_label(user_id: int) -> str:
    key = _session(user_id).get("add_type", "")
    if key == "garant":
        tier = _session(user_id).get("garant_tier", "regular")
        return GARANT_TIER_DEFAULTS.get(tier, {}).get("role_label", "Гарант")
    return PROFILE_TYPES.get(key, ("", ""))[0] or key


def _clear_add_state(user_id: int) -> None:
    s = _session(user_id)
    for key in (
        "flow", "add_type", "add_mode", "garant_tier", "target",
        "reason", "photo_file", "profile_text", "edit_entry",
    ):
        s.pop(key, None)


async def _show_menu(
    message: Message,
    user_id: int,
    *,
    edit: bool = False,
    callback: CallbackQuery | None = None,
) -> None:
    pending = db.count_complaints()
    text = "🔒 <b>Админ-панель X-Scam</b>\n\nВыберите действие:"
    markup = admin_menu(pending)
    if edit and callback and callback.message:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=markup)


async def _finalize_add(message: Message, user_id: int) -> None:
    s = _session(user_id)
    add_type = s.get("add_type")
    target = s.get("target", {})
    reason = s.get("reason", "")
    photo_file = s.get("photo_file")
    profile_text = s.get("profile_text")
    username = target.get("username")
    user_id_target = target.get("user_id")
    target_str = format_target(username, user_id_target)

    ok = False
    if add_type == "scammer":
        ok = db.add_blacklist(
            target_username=username,
            target_id=user_id_target,
            reason=reason,
            added_by=user_id,
            photo_file=photo_file,
            profile_text=profile_text,
        )
        action = "add_blacklist"
    elif add_type == "suspicious":
        ok = db.add_suspicious(
            target_username=username,
            target_id=user_id_target,
            reason=reason,
            added_by=user_id,
            photo_file=photo_file,
            profile_text=profile_text,
        )
        action = "add_suspicious"
    elif add_type == "garant":
        uname = username or (f"id{user_id_target}" if user_id_target else "")
        tier = s.get("garant_tier", "regular")
        tier_defaults = GARANT_TIER_DEFAULTS.get(tier, GARANT_TIER_DEFAULTS["regular"])
        ok = db.append_catalog_garant({
            "username": uname,
            "channel": reason or None,
            "photo_file": photo_file,
            "profile_text": profile_text,
            "telegram_id": user_id_target,
            **tier_defaults,
        })
        action = f"add_garant_{tier}"
    else:
        await message.answer("⚠️ Неизвестный тип записи.")
        _clear_add_state(user_id)
        await _show_menu(message, user_id)
        return

    type_label = _add_type_label(user_id)
    _clear_add_state(user_id)

    if ok:
        db.log_admin(user_id, action, f"{type_label} {target_str}")
        photo_note = "своё фото" if photo_file else "шаблон"
        text_note = "кастом-текст" if profile_text else "авто-текст"
        await message.answer(
            f"✅ {target_str} добавлен как <b>{type_label}</b> ({photo_note}, {text_note}).",
            parse_mode="HTML",
        )
    else:
        await message.answer(f"⚠️ {target_str} уже есть в базе ({type_label}).")
    await _show_menu(message, user_id)


@router.message(CommandStart())
async def admin_start(message: Message) -> None:
    uid = message.from_user.id if message.from_user else 0
    _sessions.pop(uid, None)
    _session(uid)["awaiting_password"] = True
    await message.answer("🔒 Админ-панель X-Scam\n\nВведите пароль:")


@router.message(F.text & ~F.text.startswith("/"))
async def password_and_flows(message: Message) -> None:
    if not message.from_user:
        return
    uid = message.from_user.id
    s = _session(uid)
    text = (message.text or "").strip()

    if s.get("awaiting_password"):
        if text != ADMIN_PASSWORD:
            await message.answer("❌ Неверный пароль. /start")
            return
        s.pop("awaiting_password", None)
        s["admin_auth"] = True
        try:
            await message.delete()
        except Exception:
            pass
        db.log_admin(uid, "login")
        await _show_menu(message, uid)
        return

    if not _is_auth(uid):
        return

    flow = s.get("flow")

    if flow == "edit_entry_find":
        if await handle_find_query(message, text, s):
            return

    if flow == "edit_entry_text":
        html_text = message_to_storage_html(message)
        if await handle_text_flow(message, html_text, s, uid):
            return

    if flow == "add_custom_text":
        if text.lower() in ("/cancel", "cancel"):
            _clear_add_state(uid)
            await message.answer("Отменено.")
            await _show_menu(message, uid)
            return
        if len(text) < 3:
            await message.answer("Слишком короткий текст.")
            return
        s["profile_text"] = message_to_storage_html(message)
        s["flow"] = "add_photo"
        type_label = _add_type_label(uid)
        await message.answer(
            f"📷 Отправьте фото для «{type_label}»\n"
            f"или <b>/skip</b> — шаблон из папки.",
            parse_mode="HTML",
        )
        return

    if await handle_text_flow(message, text, s, uid):
        return

    if flow == "add_photo" and text.lower() in ("/skip", "skip"):
        await _finalize_add(message, uid)
        return

    if flow == "add_target":
        parsed = parse_target(text)
        if not parsed:
            await message.answer("Не распознано. Пример: @username")
            return
        s["target"] = {"username": parsed.username, "user_id": parsed.user_id}
        type_label = _add_type_label(uid)
        if s.get("add_mode") == "custom":
            s["flow"] = "add_custom_text"
            from admin.entry_editor import PROFILE_TEXT_HINT

            await message.answer(
                f"✨ <b>Кастомный режим</b> — {type_label}\n\n{PROFILE_TEXT_HINT}",
                parse_mode="HTML",
            )
            return
        s["flow"] = "add_reason"
        if s.get("add_type") == "garant":
            hint = "Введите канал гаранта (или «-» без канала):"
        else:
            hint = f"Введите причину для «{type_label}» (или «-» без причины):"
        await message.answer(hint)
        return

    if flow == "add_reason":
        s["reason"] = "" if text == "-" else text
        s["flow"] = "add_photo"
        type_label = _add_type_label(uid)
        await message.answer(
            f"📷 Отправьте фото профиля для «{type_label}»\n"
            f"или напишите <b>/skip</b> — будет шаблон из папки «взгляд».",
            parse_mode="HTML",
        )
        return

    if flow == "add_photo":
        await message.answer("Отправьте фото или напишите /skip")
        return

    if flow in ("del_target", "find_target"):
        parsed = parse_target(text)
        if not parsed:
            await message.answer("Не распознано. Пример: @username")
            return
        target_str = format_target(parsed.username, parsed.user_id)
        if flow == "del_target":
            ok = db.remove_blacklist(parsed.username, parsed.user_id)
            s.pop("flow", None)
            if ok:
                db.log_admin(uid, "remove_blacklist", target_str)
                await message.answer(f"✅ {target_str} удалён из базы.")
            else:
                await message.answer(f"⚠️ {target_str} не найден в базе.")
        else:
            entry = db.find_blacklist(parsed.username, parsed.user_id)
            s.pop("flow", None)
            if entry:
                await message.answer(
                    f"🔍 <b>{target_str}</b>\n\n"
                    f"Причина: {entry.get('reason') or '—'}\n"
                    f"Добавлен: {entry.get('created_at', '')[:10]}",
                    parse_mode="HTML",
                )
            else:
                await message.answer(f"🔍 {target_str} — не найден в базе.")
        await _show_menu(message, uid)
        return

    if flow == "edit_reason":
        entry_id = s.get("edit_entry_id")
        if entry_id and db.update_blacklist_reason(entry_id, text):
            db.log_admin(uid, "edit_blacklist", f"id={entry_id}")
            await message.answer("✅ Причина обновлена.")
        else:
            await message.answer("⚠️ Не удалось обновить.")
        s.pop("flow", None)
        s.pop("edit_entry_id", None)
        await _show_menu(message, uid)
        return

    if flow == "broadcast_text":
        if len(text) < 2:
            await message.answer("Слишком короткое сообщение.")
            return
        s["broadcast_text"] = text
        s.pop("flow", None)
        recipients = len(db.get_all_user_ids())
        await message.answer(
            f"📢 <b>Предпросмотр рассылки</b>\n\n{text}\n\n"
            f"Получателей: <b>{recipients}</b>",
            parse_mode="HTML",
            reply_markup=broadcast_confirm(),
        )
        return


@router.message(F.photo)
async def photo_message(message: Message, bot: Bot) -> None:
    if not message.from_user:
        return
    uid = message.from_user.id
    flow = _session(uid).get("flow")
    if not _is_auth(uid) or flow not in ("add_photo", "edit_entry_photo"):
        return
    if not message.photo:
        return

    buf = BytesIO()
    await bot.download(message.photo[-1], destination=buf)
    photo_bytes = buf.getvalue()

    if flow == "edit_entry_photo":
        ctx = _session(uid).get("edit_entry") or {}
        entry_type = ctx.get("type", "scammer")
        entry = None
        if ctx.get("id"):
            from shared.entry_store import get_entry

            entry = get_entry(entry_type, ctx["id"])
        if entry_type == "garant" and entry:
            stem = (entry.get("username") or "garant").lstrip("@")
        elif entry:
            stem = entry.get("target_username") or str(entry.get("target_id") or "user")
        else:
            stem = "user"
        group = {"scammer": "scammer", "suspicious": "suspicious", "garant": "garant"}.get(
            entry_type, "scammer"
        )
        if await handle_photo_upload(message, photo_bytes, _session(uid), kind=group, stem=stem):
            return

    target = _session(uid).get("target", {})
    stem = target.get("username") or str(target.get("user_id") or "user")
    add_type = _session(uid).get("add_type", "scammer")
    _session(uid)["photo_file"] = save_custom_photo(
        photo_bytes,
        kind=add_type,
        stem=stem,
    )
    await _finalize_add(message, uid)


async def _show_blacklist_page(callback: CallbackQuery, page: int) -> None:
    total = db.count_blacklist()
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    items = db.list_blacklist(limit=PAGE_SIZE, offset=page * PAGE_SIZE)
    if not items:
        if callback.message:
            await callback.message.edit_text("📁 База пуста.", reply_markup=admin_menu())
        return
    lines = [f"📁 <b>База скамеров</b> ({total} записей)\n"]
    kb_rows = []
    for entry in items:
        target = format_target(entry.get("target_username"), entry.get("target_id"))
        lines.append(f"#{entry['id']} {target}")
        kb_rows.append([
            InlineKeyboardButton(text=f"#{entry['id']} {target}", callback_data=f"adm:bview:{entry['id']}")
        ])
    nav = page_nav("adm:list", page, total_pages)
    if callback.message:
        await callback.message.edit_text(
            "\n".join(lines),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows + nav.inline_keyboard),
        )


async def _show_complaints_page(
    callback: CallbackQuery,
    page: int,
    *,
    all_history: bool = False,
) -> None:
    status = None if all_history else db.COMPLAINT_PENDING
    total = db.count_complaints(status)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    items = db.list_complaints(status=status, limit=PAGE_SIZE, offset=page * PAGE_SIZE)
    title = "📜 История жалоб" if all_history else "📋 Жалобы на рассмотрении"
    prefix = "adm:chistory" if all_history else "adm:complaints"
    if not items:
        if callback.message:
            await callback.message.edit_text(f"{title}: пусто.", reply_markup=admin_menu())
        return
    lines = [f"<b>{title}</b> ({total})\n"]
    kb_rows = []
    for c in items:
        target = format_target(c.get("target_username"), c.get("target_id"))
        status_label = c.get("status", "")
        lines.append(f"#{c['id']} {target} [{status_label}]")
        kb_rows.append([
            InlineKeyboardButton(
                text=f"#{c['id']} {target}",
                callback_data=f"adm:cview:{c['id']}",
            )
        ])
    nav = page_nav(prefix, page, total_pages)
    if callback.message:
        await callback.message.edit_text(
            "\n".join(lines),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows + nav.inline_keyboard),
        )


async def _send_template_preview(callback: CallbackQuery, profile_type: str) -> None:
    label = PROFILE_TYPES.get(profile_type, ("Профиль", ""))[0]
    path = template_preview_path(profile_type)
    caption = f"🖼 <b>Шаблон: {label}</b>\n\nФутаж без юзеров и ссылок."
    markup = template_preview_menu()
    if callback.message:
        if path:
            await callback.message.answer_photo(
                FSInputFile(path),
                caption=caption,
                parse_mode="HTML",
                reply_markup=markup,
            )
        else:
            await callback.message.answer(
                f"{caption}\n\n⚠️ Файл шаблона не найден.",
                parse_mode="HTML",
                reply_markup=markup,
            )


@router.callback_query(F.data == "adm:noop")
async def noop_callback(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(F.data.startswith("adm:"))
async def admin_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    if not callback.from_user or not callback.message:
        return
    uid = callback.from_user.id
    data = callback.data or ""

    if not _is_auth(uid) and data != "adm:menu":
        await callback.message.edit_text("Сессия истекла. /start")
        return

    if data == "adm:menu":
        _clear_add_state(uid)
        _session(uid).pop("broadcast_text", None)
        _session(uid).pop("edit_entry_id", None)
        await _show_menu(callback.message, uid, edit=True, callback=callback)
        return

    if data == "adm:entries" or data.startswith("adm:e"):
        if await process_entry_callback(callback, data, _session(uid), uid):
            return

    if data == "adm:add":
        await callback.message.edit_text(
            "➕ <b>Добавить в базу</b>\n\nВыберите тип записи или посмотрите шаблоны фото:",
            parse_mode="HTML",
            reply_markup=add_type_menu(),
        )
        return

    if data == "adm:previews":
        await callback.message.edit_text(
            "🖼 <b>Шаблоны профилей</b>\n\nТак будут выглядеть карточки без своего фото:",
            parse_mode="HTML",
            reply_markup=template_preview_menu(),
        )
        return

    if data.startswith("adm:preview:"):
        await _send_template_preview(callback, data.split(":")[-1])
        return

    if data.startswith("adm:addtype:"):
        parts = data.split(":")
        add_type = parts[2] if len(parts) > 2 else parts[-1]
        if add_type not in ("scammer", "suspicious", "garant"):
            return
        _session(uid)["add_type"] = add_type
        if add_type == "garant":
            tier = parts[3] if len(parts) > 3 else "regular"
            if tier not in GARANT_TIER_DEFAULTS:
                tier = "regular"
            _session(uid)["garant_tier"] = tier
            type_label = GARANT_TIER_DEFAULTS[tier]["role_label"]
        else:
            _session(uid).pop("garant_tier", None)
            type_label = PROFILE_TYPES[add_type][0]
        await callback.message.edit_text(
            f"➕ <b>{type_label}</b>\n\nКак добавить?",
            parse_mode="HTML",
            reply_markup=add_mode_menu(add_type),
        )
        return

    if data.startswith("adm:addmode:"):
        parts = data.split(":")
        if len(parts) < 4:
            return
        mode, add_type = parts[2], parts[3]
        if add_type not in ("scammer", "suspicious", "garant"):
            return
        _session(uid)["add_type"] = add_type
        _session(uid)["add_mode"] = mode
        _session(uid)["flow"] = "add_target"
        type_label = PROFILE_TYPES[add_type][0]
        mode_label = "кастомный" if mode == "custom" else "стандартный"
        await callback.message.edit_text(
            f"➕ <b>{type_label}</b> ({mode_label})\n\nВведите @username, t.me/... или ID:",
            parse_mode="HTML",
        )
        return

    if data == "adm:del":
        _session(uid)["flow"] = "del_target"
        await callback.message.edit_text("➖ Введите @username, t.me/... или ID для удаления:")
        return

    if data == "adm:find":
        _session(uid)["flow"] = "find_target"
        await callback.message.edit_text("🔍 Введите @username, t.me/... или ID:")
        return

    if data.startswith("adm:list:"):
        await _show_blacklist_page(callback, int(data.split(":")[-1]))
        return

    if data.startswith("adm:bview:"):
        eid = int(data.split(":")[-1])
        entry = db.get_blacklist_entry(eid)
        if not entry:
            await callback.message.edit_text("Запись не найдена.", reply_markup=admin_menu())
            return
        target = format_target(entry.get("target_username"), entry.get("target_id"))
        photo_note = "своё фото" if entry.get("photo_file") else "шаблон"
        await callback.message.edit_text(
            f"📁 <b>#{eid}</b> {target}\n\n"
            f"Причина: {entry.get('reason') or '—'}\n"
            f"Фото: {photo_note}\n"
            f"Добавлен: {entry.get('created_at', '')[:10]}",
            parse_mode="HTML",
            reply_markup=blacklist_entry_actions(eid),
        )
        return

    if data.startswith("adm:edit:"):
        eid = int(data.split(":")[-1])
        _session(uid)["flow"] = "edit_reason"
        _session(uid)["edit_entry_id"] = eid
        await callback.message.edit_text(f"✏️ Новая причина для #{eid}:")
        return

    if data.startswith("adm:delid:"):
        eid = int(data.split(":")[-1])
        entry = db.get_blacklist_entry(eid)
        if entry:
            db.remove_blacklist(entry.get("target_username"), entry.get("target_id"))
            target = format_target(entry.get("target_username"), entry.get("target_id"))
            db.log_admin(uid, "remove_blacklist", target)
            await callback.message.edit_text(f"✅ {target} удалён.", reply_markup=admin_menu())
        else:
            await callback.message.edit_text("Запись не найдена.", reply_markup=admin_menu())
        return

    if data == "adm:stats":
        s = db.get_stats()
        await callback.message.edit_text(
            f"📊 <b>Статистика</b>\n\n"
            f"👤 Пользователей бота: {s['total_users']}\n"
            f"⚠️ Скамеров в базе: {s['blacklist_count']}\n"
            f"❓ Подозрительных: {db.count_suspicious()}\n"
            f"🛡 Гарантов: {db.count_catalog_garants()}\n"
            f"👨‍💼 Админов: {db.count_catalog_admins()}\n"
            f"🔍 Проверок всего: {s['checks_total']}\n"
            f"🔍 Проверок за месяц: {s['checks_month']}\n"
            f"📋 Жалоб на рассмотрении: {s['complaints_pending']}\n"
            f"📋 Жалоб всего: {s['complaints_total']}",
            parse_mode="HTML",
            reply_markup=admin_menu(s["complaints_pending"]),
        )
        return

    if data == "adm:import":
        _session(uid)["flow"] = "import_db"
        await callback.message.edit_text(
            "📥 <b>Импорт базы из файла .db</b>\n\n"
            "Отправьте файл <b>.db</b> (SQLite) с сервера оригинального бота.\n\n"
            "Или положите файл в папку бота:\n"
            f"<code>data/original_xscam.db</code>",
            parse_mode="HTML",
        )
        return

    if data == "adm:check_emojis":
        await callback.message.edit_text("🎨 Проверяю премиум-эмодзи @Xscamss_bot…")
        main_token = os.getenv("BOT_TOKEN", "").strip()
        if not main_token:
            await callback.message.edit_text(
                "❌ BOT_TOKEN не задан в .env",
                reply_markup=admin_menu(db.count_complaints()),
            )
            return
        proxy = os.getenv("PROXY", "socks5://127.0.0.1:10808").strip() or None
        session = AiohttpSession(proxy=proxy) if proxy else None
        main_bot = Bot(token=main_token, session=session) if session else Bot(token=main_token)
        try:
            _, report = await check_emoji_availability(main_bot)
            db.log_admin(uid, "check_emojis")
            await callback.message.edit_text(
                report,
                parse_mode="HTML",
                reply_markup=admin_menu(db.count_complaints()),
            )
        except Exception as exc:
            logger.exception("check_emojis failed")
            await callback.message.edit_text(
                f"❌ Ошибка проверки: {exc}\n\nПроверьте VPN/прокси.",
                reply_markup=admin_menu(db.count_complaints()),
            )
        finally:
            await main_bot.session.close()
        return

    if data == "adm:broadcast":
        _session(uid)["flow"] = "broadcast_text"
        _session(uid).pop("broadcast_text", None)
        total = len(db.get_all_user_ids())
        await callback.message.edit_text(
            f"📢 <b>Рассылка</b>\n\nВведите текст ({total} получателей):",
            parse_mode="HTML",
        )
        return

    if data == "adm:bconfirm":
        text = _session(uid).get("broadcast_text")
        if not text:
            await callback.message.edit_text("Текст рассылки не найден.")
            return
        user_ids = db.get_all_user_ids()
        await callback.message.edit_text(f"📢 Рассылка... ({len(user_ids)} получателей)")
        sent, failed = await broadcast_async(user_ids, text)
        db.log_broadcast(uid, text, sent, failed)
        db.log_admin(uid, "broadcast", f"sent={sent} failed={failed}")
        _session(uid).pop("broadcast_text", None)
        await callback.message.answer(
            f"✅ Рассылка завершена.\nОтправлено: {sent}\nОшибок: {failed}",
            reply_markup=admin_menu(db.count_complaints()),
        )
        return

    if data.startswith("adm:complaints:"):
        await _show_complaints_page(callback, int(data.split(":")[-1]), all_history=False)
        return

    if data.startswith("adm:chistory:"):
        await _show_complaints_page(callback, int(data.split(":")[-1]), all_history=True)
        return

    if data.startswith("adm:cview:"):
        cid = int(data.split(":")[-1])
        c = db.get_complaint(cid)
        if not c:
            await callback.message.edit_text("Жалоба не найдена.", reply_markup=admin_menu())
            return
        target = format_target(c.get("target_username"), c.get("target_id"))
        reporter = c.get("reporter_username") or c.get("reporter_id")
        status = c.get("status", "")
        markup = complaint_actions(cid) if status == db.COMPLAINT_PENDING else admin_menu()
        await callback.message.edit_text(
            f"📋 <b>Жалоба #{cid}</b> [{status}]\n\n"
            f"Объект: <b>{target}</b>\n"
            f"От: {reporter}\n"
            f"Дата: {c.get('created_at', '')[:16].replace('T', ' ')}\n\n"
            f"<b>Описание:</b>\n{c.get('description') or '—'}",
            parse_mode="HTML",
            reply_markup=markup,
        )
        return

    if data.startswith("adm:capprove:"):
        cid = int(data.split(":")[-1])
        c = db.get_complaint(cid)
        if not c:
            await callback.answer("Жалоба не найдена", show_alert=True)
            return
        reason = c.get("description") or "по жалобе"
        ok = db.add_blacklist(
            target_username=c.get("target_username"),
            target_id=c.get("target_id"),
            reason=reason[:500],
            added_by=uid,
        )
        db.set_complaint_status(cid, db.COMPLAINT_APPROVED, uid)
        target = format_target(c.get("target_username"), c.get("target_id"))
        db.log_admin(uid, "approve_complaint", f"#{cid} {target}")
        msg = f"✅ Жалоба #{cid} одобрена."
        if not ok:
            msg += f"\n⚠️ {target} уже был в базе."
        else:
            msg += f"\n{target} добавлен в базу."
        await callback.message.edit_text(msg, reply_markup=admin_menu(db.count_complaints()))
        return

    if data.startswith("adm:creject:"):
        cid = int(data.split(":")[-1])
        db.set_complaint_status(cid, db.COMPLAINT_REJECTED, uid)
        db.log_admin(uid, "reject_complaint", f"#{cid}")
        await callback.message.edit_text(
            f"❌ Жалоба #{cid} отклонена.",
            reply_markup=admin_menu(db.count_complaints()),
        )
        return


@router.message(F.document)
async def document_message(message: Message, bot: Bot) -> None:
    if not message.from_user:
        return
    uid = message.from_user.id
    if not _is_auth(uid):
        return

    flow = _session(uid).get("flow")
    if flow in ("add_photo", "edit_entry_photo"):
        doc = message.document
        if doc and (doc.mime_type or "").startswith("image/"):
            buf = BytesIO()
            await bot.download(doc, destination=buf)
            photo_bytes = buf.getvalue()
            if flow == "edit_entry_photo":
                ctx = _session(uid).get("edit_entry") or {}
                entry_type = ctx.get("type", "scammer")
                from shared.entry_store import get_entry

                entry = get_entry(entry_type, ctx.get("id", 0)) if ctx.get("id") else None
                if entry_type == "garant" and entry:
                    stem = (entry.get("username") or "garant").lstrip("@")
                elif entry:
                    stem = entry.get("target_username") or str(entry.get("target_id") or "user")
                else:
                    stem = "user"
                group = {"scammer": "scammer", "suspicious": "suspicious", "garant": "garant"}.get(
                    entry_type, "scammer"
                )
                if await handle_photo_upload(message, photo_bytes, _session(uid), kind=group, stem=stem):
                    return
            target = _session(uid).get("target", {})
            stem = target.get("username") or str(target.get("user_id") or "user")
            add_type = _session(uid).get("add_type", "scammer")
            _session(uid)["photo_file"] = save_custom_photo(
                photo_bytes,
                kind=add_type,
                stem=stem,
            )
            await _finalize_add(message, uid)
            return

    if _session(uid).get("flow") != "import_db":
        return
    doc = message.document
    if not doc or not (doc.file_name or "").lower().endswith(".db"):
        await message.answer("Нужен файл .db (SQLite база оригинального бота).")
        return

    dest = BASE_DIR / "data" / "original_xscam.db"
    dest.parent.mkdir(parents=True, exist_ok=True)
    await bot.download(doc, destination=dest)
    try:
        stats = import_all_from_sqlite(dest, added_by=uid, clear_blacklist=True)
        bl = stats.get("blacklist", {})
        cat = stats.get("catalog", {})
        _session(uid).pop("flow", None)
        db.log_admin(uid, "import_db", str(stats))
        await message.answer(
            f"✅ <b>Импорт завершён</b>\n\n"
            f"Скамеров добавлено: {bl.get('added', 0)}\n"
            f"Пропущено (дубли): {bl.get('skipped', 0)}\n"
            f"В источнике было: {bl.get('total_source', 0)}\n"
            f"Гарантов в справочнике: {cat.get('garants', db.count_catalog_garants())}\n"
            f"Админов в справочнике: {cat.get('admins', db.count_catalog_admins())}",
            parse_mode="HTML",
            reply_markup=admin_menu(db.count_complaints()),
        )
    except Exception as exc:
        logger.exception("import_db")
        await message.answer(f"❌ Ошибка импорта: {exc}")


@router.message(Command("skip"))
async def skip_command(message: Message) -> None:
    if not message.from_user:
        return
    uid = message.from_user.id
    uid_flow = _session(uid).get("flow")
    if _is_auth(uid) and uid_flow == "add_photo":
        await _finalize_add(message, uid)
    elif _is_auth(uid) and uid_flow == "edit_entry_photo":
        from admin.entry_editor import handle_text_flow

        await handle_text_flow(message, "/skip", _session(uid), uid)