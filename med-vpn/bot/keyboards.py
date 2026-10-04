from aiogram.types import CopyTextButton, InlineKeyboardButton, InlineKeyboardMarkup

import plans as plans_module
import ux


def main_menu(is_admin: bool, has_access: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🔌 Подключить VPN", callback_data="myconfig")],
        [InlineKeyboardButton(text="👤 Мой доступ", callback_data="status")],
        [InlineKeyboardButton(text="💳 Продлить подписку" if has_access else "💳 Выбрать тариф", callback_data="plans")],
        [InlineKeyboardButton(text="💰 Пригласить друзей", callback_data="referral"),
         InlineKeyboardButton(text="🆘 Поддержка", callback_data="support")],
    ]
    if is_admin:
        rows.append([InlineKeyboardButton(text="🛠 Админ-панель", callback_data="admin_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def connection_menu(uri: str) -> InlineKeyboardMarkup:
    rows = []
    if 1 <= len(uri) <= 256:
        rows.append([InlineKeyboardButton(text="📋 Скопировать ссылку", copy_text=CopyTextButton(text=uri))])
    rows.extend([
        [InlineKeyboardButton(text="📱 Инструкция", callback_data="help")],
        [InlineKeyboardButton(text="🆘 Не подключается", callback_data="support")],
        [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="main_menu")],
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def platforms_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=label, callback_data="guide:" + key)]
        for key,label in [("android","Android"),("ios","iPhone / iPad"),
                          ("windows","Windows"),("macos","macOS")]
    ] + [[InlineKeyboardButton(text="⬅️ Главное меню", callback_data="main_menu")]])

def support_menu(url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✉️ Написать в поддержку", url=url)],
        [InlineKeyboardButton(text="🔌 Получить ссылку повторно", callback_data="myconfig")],
        [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="main_menu")],
    ])

def account_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔌 Подключить VPN", callback_data="myconfig")],
        [InlineKeyboardButton(text="💳 Продлить подписку", callback_data="plans")],
        [InlineKeyboardButton(text="🚫 Отозвать доступ", callback_data="revoke")],
        [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="main_menu")],
    ])


def plans_menu() -> InlineKeyboardMarkup:
    rows = []
    for p in plans_module.PLANS:
        discount = f"  (-{p.discount_percent}%)" if p.discount_percent else ""
        rows.append([InlineKeyboardButton(
            text=f"{p.emoji} {p.label} — {p.price_rub} ₽{discount}",
            callback_data=f"plan:{p.key}",
        )])
    rows.extend([
        [InlineKeyboardButton(text="ℹ️ Условия и продление", callback_data="subscription_info")],
        [InlineKeyboardButton(text="🧾 Мои платежи", callback_data="purchase_history")],
        [InlineKeyboardButton(text="🆘 Вопрос об оплате", callback_data="support")],
        [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="main_menu")],
    ])
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

def guide_menu(platform: str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, url=url)]
            for label,url in ux.HAPP_DOWNLOADS.get(platform, ())]
    rows.extend([
        [InlineKeyboardButton(text="✅ Happ установлен — получить ссылку и QR", callback_data="config:" + platform)],
        [InlineKeyboardButton(text="⬅️ Выбрать другое устройство", callback_data="help")],
        [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="main_menu")],
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def referral_menu(link: str, support_url: str) -> InlineKeyboardMarkup:
    from urllib.parse import quote
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Скопировать приглашение", copy_text=CopyTextButton(text=link))],
        [InlineKeyboardButton(text="📤 Поделиться", url="https://t.me/share/url?url=" + quote(link, safe=""))],
        [InlineKeyboardButton(text="ℹ️ Условия бонусов", callback_data="referral_rules")],
        [InlineKeyboardButton(text="💸 Обсудить выплату", url=support_url)],
        [InlineKeyboardButton(text="🔄 Обновить статистику", callback_data="referral")],
        [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="main_menu")],
    ])
