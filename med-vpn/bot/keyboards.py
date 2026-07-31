from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import plans as plans_module


def main_menu(is_admin: bool) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="💳 Тарифы", callback_data="plans")],
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


def plans_menu() -> InlineKeyboardMarkup:
    rows = []
    for p in plans_module.PLANS:
        discount = f"  (-{p.discount_percent}%)" if p.discount_percent else ""
        rows.append([InlineKeyboardButton(
            text=f"{p.emoji} {p.label} — {p.price_rub} ₽{discount}",
            callback_data=f"plan:{p.key}",
        )])
    rows.append([InlineKeyboardButton(text="⬅️ Главное меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def payment_method_menu(plan_key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💵 Оплатить рублями", callback_data=f"pay_rub:{plan_key}")],
        [InlineKeyboardButton(text="⭐ Оплатить Telegram Stars", callback_data=f"pay_stars:{plan_key}")],
        [InlineKeyboardButton(text="⬅️ Тарифы", callback_data="plans")],
    ])


def support_link_menu(url: str, plan_key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✉️ Написать в поддержку", url=url)],
        [InlineKeyboardButton(text="✅ Я оплатил(а)", callback_data=f"paid_notify:{plan_key}")],
        [InlineKeyboardButton(text="⬅️ Тарифы", callback_data="plans")],
    ])


def admin_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="👥 Список пользователей", callback_data="admin_list:0")],
        [InlineKeyboardButton(text="🚫 Сбросить бесплатный доступ", callback_data="admin_reset_free")],
        [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="main_menu")],
    ])


def reset_free_confirm(count: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"✅ Да, отключить у {count}", callback_data="admin_reset_free_confirm")],
        [InlineKeyboardButton(text="Отмена", callback_data="admin_menu")],
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
