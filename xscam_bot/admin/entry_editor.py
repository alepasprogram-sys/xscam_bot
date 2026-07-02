"""Редактор записей баз в админ-панели."""

from __future__ import annotations

from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message

from admin.keyboards import page_nav
from profile_builder import build_profile_html
from shared.entry_store import (
    ENTRY_TYPES,
    GARANT_SUBTYPES,
    GARANT_TIER_DEFAULTS,
    count_entries,
    delete_entry,
    entry_type_label,
    find_entry_anywhere,
    format_entry_summary,
    garant_list_type_for_entry,
    get_entry,
    list_entries,
    move_entry,
    resolve_list_type,
    update_garant_fields,
    update_photo,
    update_profile_text,
    update_reason,
)
from shared.parsers import format_target, parse_target
from shared.profile_photos import resolve_profile_photo

PAGE_SIZE = 5

PROFILE_TEXT_HINT = (
    "📝 <b>Кастомный текст профиля (рекомендуется)</b>\n\n"
    "Полный текст карточки — можно вставить премиум-эмодзи прямо из Telegram "
    "(перешлите готовое сообщение) или HTML-теги "
    "<code>&lt;tg-emoji emoji-id=\"...\"&gt;…&lt;/tg-emoji&gt;</code>.\n\n"
    "Подстановки:\n"
    "• <code>{username}</code> — ник\n"
    "• <code>{id}</code> — Telegram ID\n"
    "• <code>{search}</code> — сколько искали\n"
    "• <code>{date}</code> — дата проверки\n"
    "• <code>{reason}</code> — причина или канал\n"
    "• <code>{bot}</code> — @Xscamss_bot\n\n"
    "ID: <code>🪪id: [&lt;code&gt;{id}&lt;/code&gt;]</code>\n\n"
    "<code>/clear</code> — авто-текст\n"
    "<code>/cancel</code> — отмена"
)


def entries_type_menu() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"adm:elist:{key}:0")]
        for key, (label, _, _) in ENTRY_TYPES.items()
        if key != "garant"
    ]
    for key, (label, _) in GARANT_SUBTYPES.items():
        rows.append([InlineKeyboardButton(text=label, callback_data=f"adm:elist:{key}:0")])
    rows.append([InlineKeyboardButton(text="🔍 Найти запись", callback_data="adm:efind")])
    rows.append([InlineKeyboardButton(text="🏠 Меню", callback_data="adm:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _list_type_label(list_type: str) -> str:
    if list_type in GARANT_SUBTYPES:
        return GARANT_SUBTYPES[list_type][0]
    return entry_type_label(list_type)


def garant_data_menu(entry_type: str, entry_id: int, entry: dict) -> InlineKeyboardMarkup:
    tier = entry.get("tier", "elite")
    rows = [
        [
            InlineKeyboardButton(text="📈 Рейтинг", callback_data=f"adm:efld:rating:{entry_type}:{entry_id}"),
            InlineKeyboardButton(text="📊 Пруфы", callback_data=f"adm:efld:proofs:{entry_type}:{entry_id}"),
        ],
        [
            InlineKeyboardButton(text="🏷 Роль", callback_data=f"adm:efld:role:{entry_type}:{entry_id}"),
            InlineKeyboardButton(text="🚩 Флаг", callback_data=f"adm:efld:flag:{entry_type}:{entry_id}"),
        ],
    ]
    if tier == "top":
        rows.append([
            InlineKeyboardButton(
                text="🔄 Сделки",
                callback_data=f"adm:efld:deals:{entry_type}:{entry_id}",
            ),
        ])
    else:
        rows.append([
            InlineKeyboardButton(
                text="💰 Стоимость",
                callback_data=f"adm:efld:price:{entry_type}:{entry_id}",
            ),
        ])
    rows.append([
        InlineKeyboardButton(
            text="👥 Ручения",
            callback_data=f"adm:efld:handlers:{entry_type}:{entry_id}",
        ),
    ])
    rows.append([
        InlineKeyboardButton(
            text="← Назад",
            callback_data=f"adm:eview:{entry_type}:{entry_id}",
        ),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def entry_actions_keyboard(
    entry_type: str,
    entry_id: int,
    *,
    list_type: str | None = None,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="📷 Фото", callback_data=f"adm:ephoto:{entry_type}:{entry_id}"),
            InlineKeyboardButton(
                text="📝 Кастом (реком.)",
                callback_data=f"adm:etext:{entry_type}:{entry_id}",
            ),
        ],
        [
            InlineKeyboardButton(text="✏️ Причина/канал", callback_data=f"adm:ereason:{entry_type}:{entry_id}"),
            InlineKeyboardButton(text="🔄 База", callback_data=f"adm:emove:{entry_type}:{entry_id}"),
        ],
    ]
    if entry_type == "garant":
        rows.append([
            InlineKeyboardButton(
                text="⚙️ Данные гаранта",
                callback_data=f"adm:edata:{entry_type}:{entry_id}",
            ),
        ])
        rows.append([
            InlineKeyboardButton(text="👑 Элит", callback_data=f"adm:etier:elite:{entry_type}:{entry_id}"),
            InlineKeyboardButton(text="🏆 Топ", callback_data=f"adm:etier:top:{entry_type}:{entry_id}"),
            InlineKeyboardButton(text="🛡 Обычн.", callback_data=f"adm:etier:regular:{entry_type}:{entry_id}"),
        ])
    back_list = list_type or entry_type
    rows.extend([
        [
            InlineKeyboardButton(text="👁 Превью", callback_data=f"adm:epreview:{entry_type}:{entry_id}"),
            InlineKeyboardButton(text="🖼 Текущее фото", callback_data=f"adm:ephshow:{entry_type}:{entry_id}"),
        ],
        [InlineKeyboardButton(text="➖ Удалить", callback_data=f"adm:edel:{entry_type}:{entry_id}")],
        [
            InlineKeyboardButton(text="К списку", callback_data=f"adm:elist:{back_list}:0"),
            InlineKeyboardButton(text="🏠 Меню", callback_data="adm:menu"),
        ],
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def entry_move_menu(entry_type: str, entry_id: int) -> InlineKeyboardMarkup:
    rows = []
    for key, (label, _, _) in ENTRY_TYPES.items():
        if key != entry_type:
            rows.append([
                InlineKeyboardButton(
                    text=f"→ {label}",
                    callback_data=f"adm:emoveto:{key}:{entry_type}:{entry_id}",
                )
            ])
    rows.append([
        InlineKeyboardButton(
            text="← Назад",
            callback_data=f"adm:eview:{entry_type}:{entry_id}",
        )
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _entry_username_user_id(entry_type: str, entry: dict) -> tuple[str | None, int | None]:
    if entry_type == "garant":
        return (
            (entry.get("username") or "").lstrip("@").lower() or None,
            entry.get("telegram_id") or entry.get("target_id"),
        )
    return entry.get("target_username"), entry.get("target_id")


def _entry_list_label(entry_type: str, entry: dict) -> str:
    if entry_type == "garant":
        return entry.get("username") or f"#{entry.get('id')}"
    return format_target(entry.get("target_username"), entry.get("target_id"))


async def show_entries_menu(message: Message, *, edit: bool = False) -> None:
    text = (
        "✏️ <b>Редактор записей</b>\n\n"
        "Выберите базу для просмотра и редактирования:\n"
        "• фото профиля\n"
        "• кастомный текст с премиум-эмодзи (рекомендуется)\n"
        "• причина / канал\n"
        "• данные гаранта (рейтинг, пруфы, ручения…)\n"
        "• тир гаранта (элит / топ / обычный)\n"
        "• перенос между базами"
    )
    markup = entries_type_menu()
    if edit:
        await message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=markup)


async def show_entry_list(callback: CallbackQuery, list_type: str, page: int) -> None:
    total = count_entries(list_type)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    items = list_entries(list_type, limit=PAGE_SIZE, offset=page * PAGE_SIZE)
    label = _list_type_label(list_type)
    base_type, _ = resolve_list_type(list_type)

    if not items:
        if callback.message:
            await callback.message.edit_text(
                f"{label}: пусто.",
                reply_markup=entries_type_menu(),
            )
        return

    lines = [f"<b>{label}</b> ({total} записей)\n"]
    kb_rows = []
    for entry in items:
        eid = entry["id"]
        target = _entry_list_label(base_type, entry)
        photo = "📷" if entry.get("photo_file") else "🖼"
        custom = "📝" if (entry.get("profile_text") or "").strip() else ""
        lines.append(f"#{eid} {photo}{custom} {target}")
        kb_rows.append([
            InlineKeyboardButton(
                text=f"#{eid} {target[:28]}",
                callback_data=f"adm:eview:{base_type}:{eid}:{list_type}",
            )
        ])
    nav = page_nav(f"adm:elist:{list_type}", page, total_pages)
    if callback.message:
        await callback.message.edit_text(
            "\n".join(lines),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows + nav.inline_keyboard),
        )


async def show_entry_detail(
    callback: CallbackQuery,
    entry_type: str,
    entry_id: int,
    *,
    list_type: str | None = None,
) -> None:
    entry = get_entry(entry_type, entry_id)
    if not callback.message:
        return
    if not entry:
        await callback.message.edit_text("Запись не найдена.", reply_markup=entries_type_menu())
        return
    if not list_type and entry_type == "garant":
        list_type = garant_list_type_for_entry(entry)
    text = format_entry_summary(entry_type, entry)
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=entry_actions_keyboard(entry_type, entry_id, list_type=list_type),
    )


async def send_entry_preview(callback: CallbackQuery, entry_type: str, entry_id: int) -> None:
    entry = get_entry(entry_type, entry_id)
    if not entry or not callback.message:
        return
    username, user_id = _entry_username_user_id(entry_type, entry)
    group = ENTRY_TYPES[entry_type][2]
    html = build_profile_html(
        username=username,
        user_id=user_id,
        checker_id=0,
        log_check=False,
    )
    photo = resolve_profile_photo(group=group, entry=entry)
    if photo:
        await callback.message.answer_photo(
            FSInputFile(photo),
            caption=html,
            parse_mode="HTML",
        )
    else:
        await callback.message.answer(html, parse_mode="HTML")


async def send_entry_photo(callback: CallbackQuery, entry_type: str, entry_id: int) -> None:
    entry = get_entry(entry_type, entry_id)
    if not entry or not callback.message:
        return
    group = ENTRY_TYPES[entry_type][2]
    photo = resolve_profile_photo(group=group, entry=entry)
    if photo:
        await callback.message.answer_photo(FSInputFile(photo), caption="Текущее фото профиля")
    else:
        await callback.message.answer("Фото не найдено.")


async def handle_find_query(message: Message, text: str, session: dict) -> bool:
    parsed = parse_target(text)
    if not parsed:
        await message.answer("Не распознано. Пример: @username или ID")
        return True
    found = find_entry_anywhere(parsed.username, parsed.user_id)
    session.pop("flow", None)
    if not found:
        target = format_target(parsed.username, parsed.user_id)
        await message.answer(f"🔍 {target} — нигде не найден.")
        return True

    for item in found:
        etype = item["entry_type"]
        entry = item["entry"]
        eid = entry.get("id")
        if not eid:
            continue
        await message.answer(
            format_entry_summary(etype, entry),
            parse_mode="HTML",
            reply_markup=entry_actions_keyboard(etype, int(eid)),
        )
    return True


async def handle_text_flow(message: Message, text: str, session: dict, admin_id: int) -> bool:
    flow = session.get("flow")
    ctx = session.get("edit_entry") or {}
    entry_type = ctx.get("type")
    entry_id = ctx.get("id")
    if not entry_type or not entry_id:
        return False

    if text.lower() in ("/cancel", "cancel"):
        session.pop("flow", None)
        session.pop("edit_entry", None)
        await message.answer("Отменено.")
        return True

    if flow == "edit_entry_text":
        if text.lower() in ("/clear", "clear"):
            ok = update_profile_text(entry_type, entry_id, None)
            session.pop("flow", None)
            session.pop("edit_entry", None)
            await message.answer("✅ Авто-текст восстановлен." if ok else "⚠️ Ошибка.")
            return True
        ok = update_profile_text(entry_type, entry_id, text)
        session.pop("flow", None)
        session.pop("edit_entry", None)
        await message.answer("✅ Текст профиля сохранён." if ok else "⚠️ Ошибка.")
        return True

    if flow == "edit_entry_reason":
        reason = "" if text == "-" else text
        ok = update_reason(entry_type, entry_id, reason)
        session.pop("flow", None)
        session.pop("edit_entry", None)
        hint = "канал" if entry_type == "garant" else "причина"
        await message.answer(f"✅ {hint.capitalize()} обновлена." if ok else "⚠️ Ошибка.")
        return True

    if flow == "edit_garant_field":
        field = ctx.get("field")
        ok = False
        if field == "rating":
            parts = text.split()
            rating = parts[0] if parts else "5.0/5"
            votes = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
            updates = {"rating": rating}
            if votes is not None:
                updates["rating_votes"] = votes
            ok = update_garant_fields(entry_id, **updates)
        elif field == "proofs":
            ok = update_garant_fields(entry_id, proofs=text)
        elif field == "role":
            ok = update_garant_fields(entry_id, role_label=text)
        elif field == "flag":
            ok = update_garant_fields(entry_id, flag=text)
        elif field == "price":
            ok = update_garant_fields(entry_id, deal_price=text)
        elif field == "deals":
            ok = update_garant_fields(entry_id, deals_count=int(text)) if text.isdigit() else False
        elif field == "handlers":
            handlers = [line.strip() for line in text.splitlines() if line.strip()]
            if text == "-":
                handlers = []
            ok = update_garant_fields(entry_id, handlers=handlers)
        session.pop("flow", None)
        session.pop("edit_entry", None)
        await message.answer("✅ Данные гаранта обновлены." if ok else "⚠️ Ошибка.")
        return True

    if flow == "edit_entry_photo" and text.lower() in ("/skip", "skip"):
        ok = update_photo(entry_type, entry_id, None)
        session.pop("flow", None)
        session.pop("edit_entry", None)
        await message.answer("✅ Сброшено на шаблон." if ok else "⚠️ Ошибка.")
        return True

    return False


async def handle_photo_upload(
    message: Message,
    photo_bytes: bytes,
    session: dict,
    *,
    kind: str,
    stem: str,
) -> bool:
    if session.get("flow") != "edit_entry_photo":
        return False
    ctx = session.get("edit_entry") or {}
    entry_type = ctx.get("type")
    entry_id = ctx.get("id")
    if not entry_type or not entry_id:
        return False

    from shared.profile_photos import save_custom_photo

    filename = save_custom_photo(photo_bytes, kind=kind, stem=stem)
    ok = update_photo(entry_type, entry_id, filename)
    session.pop("flow", None)
    session.pop("edit_entry", None)
    await message.answer("✅ Фото обновлено." if ok else "⚠️ Ошибка.")
    return True


async def process_entry_callback(
    callback: CallbackQuery,
    data: str,
    session: dict,
    admin_id: int,
) -> bool:
    """Обработка adm:e* callback. Возвращает True если обработано."""
    if data == "adm:entries":
        if callback.message:
            await show_entries_menu(callback.message, edit=True)
        return True

    if data == "adm:efind":
        session["flow"] = "edit_entry_find"
        if callback.message:
            await callback.message.edit_text("🔍 Введите @username, t.me/... или ID:")
        return True

    if data.startswith("adm:elist:"):
        parts = data.split(":")
        entry_type, page = parts[2], int(parts[3])
        await show_entry_list(callback, entry_type, page)
        return True

    if data.startswith("adm:eview:"):
        parts = data.split(":")
        entry_type, eid = parts[2], int(parts[3])
        list_type = parts[4] if len(parts) > 4 else None
        await show_entry_detail(callback, entry_type, eid, list_type=list_type)
        return True

    if data.startswith("adm:edata:"):
        _, _, entry_type, eid = data.split(":", 3)
        entry = get_entry(entry_type, int(eid))
        if callback.message and entry:
            await callback.message.edit_text(
                format_entry_summary(entry_type, entry),
                parse_mode="HTML",
                reply_markup=garant_data_menu(entry_type, int(eid), entry),
            )
        return True

    if data.startswith("adm:efld:"):
        _, _, field, entry_type, eid = data.split(":", 4)
        hints = {
            "rating": "📈 Рейтинг (пример: 5.0/5 или 5.0/5 12 для голосов):",
            "proofs": "📊 Пруфы (пример: 12000+):",
            "role": "🏷 Роль (пример: Элитный гарант):",
            "flag": "🚩 Флаг (пример: 🇷🇺 или ⚡):",
            "price": "💰 Стоимость сделки (пример: 0 или 100₽):",
            "deals": "🔄 Количество сделок (число):",
            "handlers": "👥 Ручения — по одному @ник на строку (или «-» очистить):",
        }
        session["edit_entry"] = {"type": entry_type, "id": int(eid), "field": field}
        session["flow"] = "edit_garant_field"
        if callback.message:
            await callback.message.edit_text(
                f"{hints.get(field, 'Введите значение:')}\n/cancel — отмена"
            )
        return True

    if data.startswith("adm:ephoto:"):
        _, _, entry_type, eid = data.split(":", 3)
        session["edit_entry"] = {"type": entry_type, "id": int(eid)}
        session["flow"] = "edit_entry_photo"
        if callback.message:
            await callback.message.edit_text(
                "📷 Отправьте новое фото.\n/skip — сбросить на шаблон\n/cancel — отмена"
            )
        return True

    if data.startswith("adm:etext:"):
        _, _, entry_type, eid = data.split(":", 3)
        session["edit_entry"] = {"type": entry_type, "id": int(eid)}
        session["flow"] = "edit_entry_text"
        entry = get_entry(entry_type, int(eid))
        current = (entry or {}).get("profile_text") or ""
        preview = f"\n\n<b>Сейчас:</b>\n<code>{current[:500]}</code>" if current else "\n\n<i>Авто-текст</i>"
        if callback.message:
            await callback.message.edit_text(PROFILE_TEXT_HINT + preview, parse_mode="HTML")
        return True

    if data.startswith("adm:ereason:"):
        _, _, entry_type, eid = data.split(":", 3)
        session["edit_entry"] = {"type": entry_type, "id": int(eid)}
        session["flow"] = "edit_entry_reason"
        hint = "канал гаранта" if entry_type == "garant" else "причину"
        if callback.message:
            await callback.message.edit_text(
                f"✏️ Введите {hint} (или «-» без текста):\n/cancel — отмена"
            )
        return True

    if data.startswith("adm:emove:"):
        _, _, entry_type, eid = data.split(":", 3)
        if callback.message:
            await callback.message.edit_text(
                "🔄 <b>Перенести в другую базу</b>",
                parse_mode="HTML",
                reply_markup=entry_move_menu(entry_type, int(eid)),
            )
        return True

    if data.startswith("adm:etier:"):
        _, _, tier, entry_type, eid = data.split(":", 4)
        tier_defaults = GARANT_TIER_DEFAULTS.get(tier, GARANT_TIER_DEFAULTS["regular"])
        from shared import database as db

        ok = db.update_entry_field(entry_type, int(eid), **tier_defaults)
        if callback.message:
            if ok:
                entry = get_entry(entry_type, int(eid))
                list_type = garant_list_type_for_entry(entry) if entry else None
                await show_entry_detail(callback, entry_type, int(eid), list_type=list_type)
            else:
                await callback.message.edit_text("⚠️ Не удалось сменить тир.")
        return True

    if data.startswith("adm:emoveto:"):
        _, _, new_type, old_type, eid = data.split(":", 4)
        ok = move_entry(old_type, int(eid), new_type, admin_id=admin_id)
        if callback.message:
            if ok:
                await callback.message.edit_text(
                    f"✅ Перенесено в {entry_type_label(new_type)}.",
                    reply_markup=entries_type_menu(),
                )
            else:
                await callback.message.edit_text("⚠️ Не удалось перенести.")
        return True

    if data.startswith("adm:epreview:"):
        _, _, entry_type, eid = data.split(":", 3)
        await send_entry_preview(callback, entry_type, int(eid))
        return True

    if data.startswith("adm:ephshow:"):
        _, _, entry_type, eid = data.split(":", 3)
        await send_entry_photo(callback, entry_type, int(eid))
        return True

    if data.startswith("adm:edel:"):
        _, _, entry_type, eid = data.split(":", 3)
        entry = get_entry(entry_type, int(eid))
        ok = delete_entry(entry_type, int(eid)) if entry else False
        if callback.message:
            if ok:
                await callback.message.edit_text("✅ Запись удалена.", reply_markup=entries_type_menu())
            else:
                await callback.message.edit_text("⚠️ Не удалось удалить.")
        return True

    return False