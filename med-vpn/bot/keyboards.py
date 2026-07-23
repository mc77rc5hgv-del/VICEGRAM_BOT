from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu(is_admin: bool) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🔑 Получить доступ", callback_data="getconfig")],
        [
            InlineKeyboardButton(text="📋 Мой конфиг", callback_data="myconfig"),
            InlineKeyboardButton(text="📊 Статус", callback_data="status"),
        ],
        [
            InlineKeyboardButton(text="❌ Отключить", callback_data="revoke"),
            InlineKeyboardButton(text="ℹ️ Помощь", callback_data="help"),
        ],
        [InlineKeyboardButton(text="💰 Реферальная программа", callback_data="referral")],
    ]
    if is_admin:
        rows.append([InlineKeyboardButton(text="🛠 Админ-панель", callback_data="admin_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="👥 Список пользователей", callback_data="admin_list:0")],
        [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="main_menu")],
    ])


def revoke_confirm() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, отключить", callback_data="revoke_confirm"),
            InlineKeyboardButton(text="Отмена", callback_data="main_menu"),
        ]
    ])


def list_pagination(offset: int, page_size: int, has_more: bool) -> InlineKeyboardMarkup:
    nav = []
    if offset > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"admin_list:{max(0, offset - page_size)}"))
    if has_more:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"admin_list:{offset + page_size}"))
    rows = [nav] if nav else []
    rows.append([InlineKeyboardButton(text="⬅️ Админ-панель", callback_data="admin_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
