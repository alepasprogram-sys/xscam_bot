from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def admin_menu(pending_complaints: int = 0) -> InlineKeyboardMarkup:
    complaints_label = (
        f"📋 Жалобы ({pending_complaints})" if pending_complaints else "📋 Жалобы"
    )
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➕ Добавить", callback_data="adm:add"),
            InlineKeyboardButton(text="➖ Удалить", callback_data="adm:del"),
        ],
        [
            InlineKeyboardButton(text="🔍 Найти", callback_data="adm:find"),
            InlineKeyboardButton(text="📁 База", callback_data="adm:list:0"),
        ],
        [InlineKeyboardButton(text="✏️ Редактор записей", callback_data="adm:entries")],
        [
            InlineKeyboardButton(text=complaints_label, callback_data="adm:complaints:0"),
            InlineKeyboardButton(text="📜 История жалоб", callback_data="adm:chistory:0"),
        ],
        [
            InlineKeyboardButton(text="📢 Рассылка", callback_data="adm:broadcast"),
            InlineKeyboardButton(text="📊 Статистика", callback_data="adm:stats"),
        ],
        [InlineKeyboardButton(text="📥 Импорт базы", callback_data="adm:import")],
        [InlineKeyboardButton(text="🎨 Проверка эмодзи", callback_data="adm:check_emojis")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="adm:menu")],
    ])


def add_type_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚨 Мошенник", callback_data="adm:addtype:scammer")],
        [InlineKeyboardButton(text="⚠️ Подозрительный", callback_data="adm:addtype:suspicious")],
        [
            InlineKeyboardButton(text="👑 Элитный", callback_data="adm:addtype:garant:elite"),
            InlineKeyboardButton(text="🏆 Топ", callback_data="adm:addtype:garant:top"),
        ],
        [InlineKeyboardButton(text="🛡 Обычный гарант", callback_data="adm:addtype:garant:regular")],
        [InlineKeyboardButton(text="🖼 Шаблоны", callback_data="adm:previews")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="adm:menu")],
    ])


def add_mode_menu(add_type: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="✨ Кастомный (рекомендуется)",
            callback_data=f"adm:addmode:custom:{add_type}",
        )],
        [InlineKeyboardButton(
            text="📋 Стандарт",
            callback_data=f"adm:addmode:standard:{add_type}",
        )],
        [InlineKeyboardButton(text="❌ Назад", callback_data="adm:add")],
    ])


def template_preview_menu() -> InlineKeyboardMarkup:
    from shared.profile_photos import PROFILE_TYPES

    rows = [
        [InlineKeyboardButton(text=f"🖼 {label}", callback_data=f"adm:preview:{key}")]
        for key, (label, _) in PROFILE_TYPES.items()
    ]
    rows.append([InlineKeyboardButton(text="❌ Назад", callback_data="adm:add")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def complaint_actions(complaint_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Одобрить → в базу", callback_data=f"adm:capprove:{complaint_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"adm:creject:{complaint_id}"),
        ],
        [
            InlineKeyboardButton(text="К списку", callback_data="adm:complaints:0"),
            InlineKeyboardButton(text="🏠 Меню", callback_data="adm:menu"),
        ],
    ])


def page_nav(prefix: str, page: int, total_pages: int) -> InlineKeyboardMarkup:
    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"{prefix}:{page - 1}"))
    buttons.append(InlineKeyboardButton(text=f"{page + 1}/{max(total_pages, 1)}", callback_data="adm:noop"))
    if page < total_pages - 1:
        buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"{prefix}:{page + 1}"))
    return InlineKeyboardMarkup(inline_keyboard=[
        buttons,
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="adm:menu")],
    ])


def blacklist_entry_actions(entry_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✏️ Изменить причину", callback_data=f"adm:edit:{entry_id}"),
            InlineKeyboardButton(text="➖ Удалить", callback_data=f"adm:delid:{entry_id}"),
        ],
        [
            InlineKeyboardButton(text="К базе", callback_data="adm:list:0"),
            InlineKeyboardButton(text="🏠 Меню", callback_data="adm:menu"),
        ],
    ])


def broadcast_confirm() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Отправить всем", callback_data="adm:bconfirm"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="adm:menu"),
        ],
    ])