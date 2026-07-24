import asyncio
import logging
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    BotCommand,
    BotCommandScopeChat,
    BotCommandScopeDefault,
    BufferedInputFile,
    CallbackQuery,
    FSInputFile,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)

import db
import hysteria_backend as hysteria
import keyboards as kb
import plans
from config import settings
from qr import config_to_qr_png

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("med-vpn-bot")

router = Router()

PAGE_SIZE = 30

USER_COMMANDS = [
    BotCommand(command="start", description="Главное меню"),
    BotCommand(command="subscribe", description="Тарифы и оплата"),
    BotCommand(command="getconfig", description="Получить ссылку подключения"),
    BotCommand(command="myconfig", description="Прислать ссылку повторно"),
    BotCommand(command="status", description="Статус подключения"),
    BotCommand(command="revoke", description="Отключить доступ"),
    BotCommand(command="referral", description="Реферальная программа"),
    BotCommand(command="help", description="Помощь"),
]

ADMIN_COMMANDS = USER_COMMANDS + [
    BotCommand(command="admin_stats", description="Статистика (админ)"),
    BotCommand(command="admin_list", description="Список пользователей (админ)"),
    BotCommand(command="admin_revoke", description="Отключить пользователя по ID (админ)"),
    BotCommand(command="admin_grant", description="Выдать подписку по ID/username (админ)"),
    BotCommand(command="admin_purchase", description="Записать покупку и начислить рефералу (админ)"),
    BotCommand(command="admin_payout", description="Отметить выплату рефералу (админ)"),
]

WELCOME_TEXT = (
    "🛡️ *Добро пожаловать в MED VPN!*\n\n"
    "VPN, который просто работает: YouTube, Telegram, ChatGPT, банки — всё открывается, "
    "без лагов и переключений.\n\n"
    "🚀 Высокая скорость\n"
    "🚫 Без рекламы\n"
    "📱 Одна подписка на все устройства\n"
    "♾️ Без ограничений по трафику\n\n"
    "Выберите действие:"
)

HELP_TEXT = (
    f"*{settings.service_name}* — VPN на Hysteria2, подключение через приложение Happ.\n\n"
    "💳 *Тарифы* — платные подписки (рубли или Telegram Stars)\n"
    "🔑 *Получить доступ* — бесплатная персональная ссылка и QR-код\n"
    "📋 *Мой конфиг* — прислать ту же ссылку ещё раз\n"
    "📊 *Статус* — когда выдан доступ и до какого числа действует подписка\n"
    "❌ *Отключить* — отозвать свой доступ\n\n"
    "Как подключиться: откройте Happ → добавьте сервер по ссылке или QR-коду → включите подключение."
)


def _build_plans_intro() -> str:
    lines = [
        f"{p.emoji} {p.label} — *{p.price_rub} ₽*" + (f" _(-{p.discount_percent}%)_" if p.discount_percent else "")
        for p in plans.PLANS
    ]
    return "💳 *Тарифы MED VPN*\n\nЧем длиннее срок — тем выгоднее подписка 🙌\n\n" + "\n".join(lines)


PLANS_INTRO = _build_plans_intro()


def _is_admin(telegram_id: int) -> bool:
    return telegram_id in settings.admin_ids


def _fmt_dt(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        return datetime.fromisoformat(iso).strftime("%d.%m.%Y %H:%M UTC")
    except ValueError:
        return iso


async def _send_welcome(bot: Bot, chat_id: int, telegram_id: int) -> None:
    markup = kb.main_menu(_is_admin(telegram_id))
    image_path = Path(settings.welcome_image_path)
    if image_path.is_file():
        await bot.send_photo(
            chat_id,
            FSInputFile(image_path),
            caption=WELCOME_TEXT,
            parse_mode="Markdown",
            reply_markup=markup,
        )
    else:
        await bot.send_message(chat_id, WELCOME_TEXT, parse_mode="Markdown", reply_markup=markup)


async def _send_config(bot: Bot, chat_id: int, client: db.Client) -> None:
    label = f"tg{client.telegram_id}"
    uri = hysteria.build_hysteria_uri(client.username, client.password, label)
    await bot.send_message(
        chat_id,
        f"✅ Ваша ссылка *{settings.service_name}* готова.\n\n"
        f"`{uri}`\n\n"
        "Откройте Happ → Добавить сервер → Из буфера обмена (или отсканируйте QR-код ниже).",
        parse_mode="Markdown",
    )
    qr_png = config_to_qr_png(uri)
    await bot.send_photo(chat_id, BufferedInputFile(qr_png.read(), filename="med-vpn-qr.png"))


async def _handle_getconfig(bot: Bot, chat_id: int, telegram_id: int, telegram_name: str | None) -> None:
    existing = db.get_active_client(telegram_id)
    if existing:
        await bot.send_message(
            chat_id,
            "У вас уже есть активная ссылка. Нажмите «Мой конфиг», чтобы получить её снова.",
            reply_markup=kb.main_menu(_is_admin(telegram_id)),
        )
        return

    username, password = hysteria.generate_credentials(telegram_id)
    try:
        hysteria.add_user(username, password)
    except hysteria.HysteriaError as exc:
        log.exception("Failed to provision client for %s", telegram_id)
        await bot.send_message(chat_id, f"⚠️ Не удалось создать ссылку: {exc}")
        return

    client = db.create_client(
        telegram_id=telegram_id,
        telegram_name=telegram_name,
        username=username,
        password=password,
    )
    await _send_config(bot, chat_id, client)


async def _handle_myconfig(bot: Bot, chat_id: int, telegram_id: int) -> None:
    client = db.get_active_client(telegram_id)
    if not client:
        await bot.send_message(
            chat_id,
            "У вас пока нет ссылки. Нажмите «Получить доступ».",
            reply_markup=kb.main_menu(_is_admin(telegram_id)),
        )
        return
    await _send_config(bot, chat_id, client)


async def _handle_status(bot: Bot, chat_id: int, telegram_id: int) -> None:
    client = db.get_active_client(telegram_id)
    if not client:
        await bot.send_message(chat_id, "🔴 Доступ не активирован.", reply_markup=kb.main_menu(_is_admin(telegram_id)))
        return
    if client.expires_at:
        text = (
            f"🟢 Доступ активен (подписка)\n"
            f"Выдан: {_fmt_dt(client.created_at)}\n"
            f"Действует до: {_fmt_dt(client.expires_at)}"
        )
    else:
        text = f"🟢 Доступ активен (бессрочный)\nВыдан: {_fmt_dt(client.created_at)}"
    await bot.send_message(chat_id, text, reply_markup=kb.main_menu(_is_admin(telegram_id)))


async def _handle_revoke(bot: Bot, chat_id: int, telegram_id: int) -> None:
    client = db.revoke_client(telegram_id)
    if not client:
        await bot.send_message(chat_id, "У вас нет активной ссылки.", reply_markup=kb.main_menu(_is_admin(telegram_id)))
        return
    try:
        hysteria.remove_user(client.username)
    except hysteria.HysteriaError:
        log.exception("Failed to remove client %s from Hysteria", client.username)
    await bot.send_message(
        chat_id,
        "Доступ отключён. Нажмите «Получить доступ», чтобы подключиться снова.",
        reply_markup=kb.main_menu(_is_admin(telegram_id)),
    )


async def _send_referral(bot: Bot, chat_id: int, telegram_id: int) -> None:
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=ref_{telegram_id}"
    stats = db.referral_stats(telegram_id)
    percent = int(settings.referral_commission_rate * 100)
    await bot.send_message(
        chat_id,
        "💰 *Реферальная программа*\n\n"
        f"Приглашайте друзей — получайте {percent}% от суммы их покупок.\n\n"
        f"Ваша ссылка:\n`{link}`\n\n"
        f"Приглашено: {stats['invited']}\n"
        f"Баланс: {stats['balance']:.2f} {settings.default_currency}",
        parse_mode="Markdown",
        reply_markup=kb.main_menu(_is_admin(telegram_id)),
    )


async def _grant_subscription(
    bot: Bot,
    telegram_id: int,
    telegram_name: str | None,
    plan: plans.Plan,
    currency: str,
    amount: float,
) -> db.Client:
    client = db.get_active_client(telegram_id)
    if not client:
        username, password = hysteria.generate_credentials(telegram_id)
        hysteria.add_user(username, password)
        client = db.create_client(
            telegram_id=telegram_id, telegram_name=telegram_name, username=username, password=password
        )
    db.extend_expiry(telegram_id, plan.months)
    db.record_purchase(telegram_id, amount, currency)
    updated = db.get_active_client(telegram_id)
    assert updated is not None
    return updated


async def _send_admin_stats(bot: Bot, chat_id: int) -> None:
    s = db.stats()
    revenue_lines = "\n".join(f"  {cur}: {total:.2f}" for cur, total in s["revenue"].items()) or "  —"
    await bot.send_message(
        chat_id,
        "📊 *Статистика*\n\n"
        f"Пользователей бота всего: {s['total_users']}\n"
        f"Активных клиентов VPN: {s['active']}\n"
        f"  — по подписке: {s['with_subscription']}\n"
        f"  — бессрочных: {s['free_unlimited']}\n"
        f"Отозвано/истекло: {s['revoked']}\n\n"
        f"Покупок: {s['purchases_count']}\n"
        f"Выручка:\n{revenue_lines}\n\n"
        f"Начислено рефералам всего: {s['commission_total']:.2f}\n"
        f"К выплате рефералам сейчас: {s['balance_owed']:.2f}",
        parse_mode="Markdown",
        reply_markup=kb.admin_menu(),
    )


async def _send_admin_list(bot: Bot, chat_id: int, offset: int) -> None:
    clients = db.list_active_clients(limit=PAGE_SIZE + 1, offset=offset)
    has_more = len(clients) > PAGE_SIZE
    clients = clients[:PAGE_SIZE]
    if not clients:
        text = "Активных пользователей нет." if offset == 0 else "Больше пользователей нет."
    else:
        # Plain text on purpose: telegram_name is a user-controlled username and may contain
        # Markdown special characters (e.g. underscores), which would otherwise break parsing
        # and silently fail to send.
        lines = []
        for c in clients:
            sub = f", до {_fmt_dt(c.expires_at)}" if c.expires_at else ", бессрочно"
            lines.append(f"{c.telegram_id} @{c.telegram_name or '-'} — {_fmt_dt(c.created_at)}{sub}")
        text = f"👥 Пользователи ({offset + 1}-{offset + len(clients)})\n\n" + "\n".join(lines)
    await bot.send_message(chat_id, text, reply_markup=kb.list_pagination(offset, PAGE_SIZE, has_more))


# ---- Commands ----

@router.message(Command("start"))
async def cmd_start(message: Message, command: CommandObject) -> None:
    telegram_id = message.from_user.id
    referred_by = None
    if command.args and command.args.startswith("ref_"):
        try:
            candidate = int(command.args.removeprefix("ref_"))
            if candidate != telegram_id:
                referred_by = candidate
        except ValueError:
            pass
    db.get_or_create_user(telegram_id, message.from_user.username, referred_by)
    await _send_welcome(message.bot, message.chat.id, telegram_id)


@router.message(Command("referral"))
async def cmd_referral(message: Message) -> None:
    await _send_referral(message.bot, message.chat.id, message.from_user.id)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT, parse_mode="Markdown", reply_markup=kb.main_menu(_is_admin(message.from_user.id)))


@router.message(Command("subscribe"))
async def cmd_subscribe(message: Message) -> None:
    await message.answer(PLANS_INTRO, parse_mode="Markdown", reply_markup=kb.plans_menu())


@router.message(Command("getconfig"))
async def cmd_getconfig(message: Message) -> None:
    await _handle_getconfig(message.bot, message.chat.id, message.from_user.id, message.from_user.username)


@router.message(Command("myconfig"))
async def cmd_myconfig(message: Message) -> None:
    await _handle_myconfig(message.bot, message.chat.id, message.from_user.id)


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    await _handle_status(message.bot, message.chat.id, message.from_user.id)


@router.message(Command("revoke"))
async def cmd_revoke(message: Message) -> None:
    await message.answer("Точно отключить доступ?", reply_markup=kb.revoke_confirm())


@router.message(Command("admin_stats"))
async def cmd_admin_stats(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return
    await _send_admin_stats(message.bot, message.chat.id)


@router.message(Command("admin_list"))
async def cmd_admin_list(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return
    await _send_admin_list(message.bot, message.chat.id, offset=0)


@router.message(Command("admin_revoke"))
async def cmd_admin_revoke(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Использование: /admin_revoke <telegram_id>")
        return
    target_id = int(parts[1])
    client = db.revoke_client(target_id)
    if not client:
        await message.answer("У этого пользователя нет активной ссылки.")
        return
    try:
        hysteria.remove_user(client.username)
    except hysteria.HysteriaError:
        log.exception("Failed to remove client %s from Hysteria", client.username)
    await message.answer(f"Доступ пользователя {target_id} отозван.")


@router.message(Command("admin_grant"))
async def cmd_admin_grant(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) != 3:
        await message.answer(
            "Использование: /admin_grant <@username или telegram_id> <тариф>\n"
            f"Тарифы: {', '.join(plans.PLANS_BY_KEY)}"
        )
        return
    target, plan_key = parts[1], parts[2]
    plan = plans.PLANS_BY_KEY.get(plan_key)
    if not plan:
        await message.answer(f"Неизвестный тариф. Доступные: {', '.join(plans.PLANS_BY_KEY)}")
        return

    raw = target.lstrip("@")
    if raw.isdigit():
        target_id = int(raw)
    else:
        found = db.find_by_username(raw)
        if not found:
            await message.answer("Пользователь не найден — он должен хотя бы раз запустить бота (/start).")
            return
        target_id = found

    try:
        client = await _grant_subscription(
            message.bot, target_id, None, plan, currency=settings.default_currency, amount=plan.price_rub
        )
    except hysteria.HysteriaError as exc:
        await message.answer(f"⚠️ Не удалось выдать доступ: {exc}")
        return

    await message.answer(f"Подписка «{plan.label}» выдана {target_id} до {_fmt_dt(client.expires_at)}.")
    try:
        await message.bot.send_message(
            target_id,
            f"✅ Вам выдана подписка *{settings.service_name}* «{plan.label}» до {_fmt_dt(client.expires_at)}.",
            parse_mode="Markdown",
        )
        await _send_config(message.bot, target_id, client)
    except Exception:
        log.exception("Failed to notify %s about granted subscription", target_id)


@router.message(Command("admin_purchase"))
async def cmd_admin_purchase(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) not in (3, 4) or not parts[1].isdigit():
        await message.answer("Использование: /admin_purchase <telegram_id> <сумма> [валюта]")
        return
    target_id = int(parts[1])
    try:
        amount = float(parts[2])
    except ValueError:
        await message.answer("Сумма должна быть числом.")
        return
    currency = parts[3] if len(parts) == 4 else settings.default_currency

    db.get_or_create_user(target_id, None)
    result = db.record_purchase(target_id, amount, currency)
    text = f"Записана покупка: {target_id} — {amount} {currency}."
    if result["referrer_id"]:
        text += f"\nНачислено рефереру {result['referrer_id']}: {result['commission']:.2f} {currency}"
    else:
        text += "\nБез реферала — начислять некому."
    await message.answer(text)


@router.message(Command("admin_payout"))
async def cmd_admin_payout(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Использование: /admin_payout <telegram_id>")
        return
    target_id = int(parts[1])
    amount = db.payout_balance(target_id)
    await message.answer(
        f"Баланс пользователя {target_id} обнулён. К выплате было: {amount:.2f} {settings.default_currency}"
    )


# ---- Subscription / payment flow ----

@router.message(F.successful_payment)
async def on_successful_payment(message: Message) -> None:
    payload = message.successful_payment.invoice_payload
    parts = payload.split(":")
    if len(parts) != 3 or parts[0] != "sub":
        log.warning("Unexpected successful_payment payload: %s", payload)
        return
    plan_key, telegram_id_str = parts[1], parts[2]
    plan = plans.PLANS_BY_KEY.get(plan_key)
    if not plan:
        log.warning("Unknown plan in payment payload: %s", payload)
        return
    telegram_id = int(telegram_id_str)

    try:
        client = await _grant_subscription(
            message.bot,
            telegram_id,
            message.from_user.username,
            plan,
            currency="XTR",
            amount=message.successful_payment.total_amount,
        )
    except hysteria.HysteriaError as exc:
        log.exception("Failed to provision client after Stars payment for %s", telegram_id)
        await message.answer(f"⚠️ Оплата прошла, но не удалось выдать доступ автоматически: {exc}. Напишите в поддержку.")
        return

    await message.answer(f"✅ Оплата получена! Подписка «{plan.label}» активна до {_fmt_dt(client.expires_at)}.")
    await _send_config(message.bot, message.chat.id, client)


# ---- Inline button callbacks ----

@router.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery) -> None:
    await callback.answer()
    await _send_welcome(callback.bot, callback.message.chat.id, callback.from_user.id)


@router.callback_query(F.data == "help")
async def cb_help(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer(
        HELP_TEXT, parse_mode="Markdown", reply_markup=kb.main_menu(_is_admin(callback.from_user.id))
    )


@router.callback_query(F.data == "plans")
async def cb_plans(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer(PLANS_INTRO, parse_mode="Markdown", reply_markup=kb.plans_menu())


@router.callback_query(F.data.startswith("plan:"))
async def cb_plan_selected(callback: CallbackQuery) -> None:
    await callback.answer()
    plan_key = callback.data.split(":", 1)[1]
    plan = plans.PLANS_BY_KEY.get(plan_key)
    if not plan:
        return
    discount = f" 🔥 экономия {plan.discount_percent}%" if plan.discount_percent else ""
    await callback.message.answer(
        f"{plan.emoji} *{plan.label}*{discount}\n\n"
        f"💰 *{plan.price_rub} ₽* (≈{plan.price_per_month:.0f} ₽/мес)\n"
        f"⭐ или *{plan.price_stars}* Telegram Stars\n\n"
        "Как хотите оплатить?",
        parse_mode="Markdown",
        reply_markup=kb.payment_method_menu(plan_key),
    )


@router.callback_query(F.data.startswith("pay_rub:"))
async def cb_pay_rub(callback: CallbackQuery) -> None:
    await callback.answer()
    plan_key = callback.data.split(":", 1)[1]
    plan = plans.PLANS_BY_KEY.get(plan_key)
    if not plan:
        return
    text = (
        f"Здравствуйте! Хочу оформить подписку {settings.service_name} «{plan.label}» "
        f"за {plan.price_rub} ₽. Пришлите, пожалуйста, реквизиты для оплаты."
    )
    url = f"https://t.me/{settings.support_username}?text={quote(text)}"
    await callback.message.answer(
        f"💵 *Оплата рублями*\n\n"
        f"Тариф: {plan.emoji} {plan.label} — *{plan.price_rub} ₽*\n\n"
        "Нажмите кнопку ниже — менеджер пришлёт реквизиты для оплаты:",
        parse_mode="Markdown",
        reply_markup=kb.support_link_menu(url),
    )


@router.callback_query(F.data.startswith("pay_stars:"))
async def cb_pay_stars(callback: CallbackQuery) -> None:
    await callback.answer()
    plan_key = callback.data.split(":", 1)[1]
    plan = plans.PLANS_BY_KEY.get(plan_key)
    if not plan:
        return
    await callback.bot.send_invoice(
        chat_id=callback.message.chat.id,
        title=f"{settings.service_name} — {plan.label}",
        description=f"Подписка {settings.service_name} на {plan.label}.",
        payload=f"sub:{plan.key}:{callback.from_user.id}",
        currency="XTR",
        prices=[LabeledPrice(label=plan.label, amount=plan.price_stars)],
    )


@router.pre_checkout_query()
async def on_pre_checkout(pre_checkout_query: PreCheckoutQuery) -> None:
    await pre_checkout_query.answer(ok=True)


@router.callback_query(F.data == "getconfig")
async def cb_getconfig(callback: CallbackQuery) -> None:
    await callback.answer("Создаю ссылку…")
    await _handle_getconfig(callback.bot, callback.message.chat.id, callback.from_user.id, callback.from_user.username)


@router.callback_query(F.data == "myconfig")
async def cb_myconfig(callback: CallbackQuery) -> None:
    await callback.answer()
    await _handle_myconfig(callback.bot, callback.message.chat.id, callback.from_user.id)


@router.callback_query(F.data == "status")
async def cb_status(callback: CallbackQuery) -> None:
    await callback.answer()
    await _handle_status(callback.bot, callback.message.chat.id, callback.from_user.id)


@router.callback_query(F.data == "revoke")
async def cb_revoke(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer("Точно отключить доступ?", reply_markup=kb.revoke_confirm())


@router.callback_query(F.data == "revoke_confirm")
async def cb_revoke_confirm(callback: CallbackQuery) -> None:
    await callback.answer()
    await _handle_revoke(callback.bot, callback.message.chat.id, callback.from_user.id)


@router.callback_query(F.data == "referral")
async def cb_referral(callback: CallbackQuery) -> None:
    await callback.answer()
    await _send_referral(callback.bot, callback.message.chat.id, callback.from_user.id)


@router.callback_query(F.data == "admin_menu")
async def cb_admin_menu(callback: CallbackQuery) -> None:
    await callback.answer()
    if not _is_admin(callback.from_user.id):
        return
    await callback.message.answer("🛠 Админ-панель", reply_markup=kb.admin_menu())


@router.callback_query(F.data == "admin_stats")
async def cb_admin_stats(callback: CallbackQuery) -> None:
    await callback.answer()
    if not _is_admin(callback.from_user.id):
        return
    await _send_admin_stats(callback.bot, callback.message.chat.id)


@router.callback_query(F.data.startswith("admin_list:"))
async def cb_admin_list(callback: CallbackQuery) -> None:
    await callback.answer()
    if not _is_admin(callback.from_user.id):
        return
    offset = int(callback.data.split(":", 1)[1])
    await _send_admin_list(callback.bot, callback.message.chat.id, offset)


async def _set_commands(bot: Bot) -> None:
    await bot.set_my_commands(USER_COMMANDS, scope=BotCommandScopeDefault())
    for admin_id in settings.admin_ids:
        try:
            await bot.set_my_commands(ADMIN_COMMANDS, scope=BotCommandScopeChat(chat_id=admin_id))
        except Exception:
            log.exception("Failed to set admin commands for %s", admin_id)


async def _expiry_sweep(bot: Bot) -> None:
    while True:
        try:
            for client in db.list_expired_clients():
                try:
                    hysteria.remove_user(client.username)
                except hysteria.HysteriaError:
                    log.exception("Failed to remove expired client %s from Hysteria", client.username)
                db.revoke_client(client.telegram_id)
                try:
                    await bot.send_message(
                        client.telegram_id,
                        f"⛔ Ваша подписка {settings.service_name} истекла. Оформите новую через /subscribe.",
                    )
                except Exception:
                    log.exception("Failed to notify %s about expired subscription", client.telegram_id)
        except Exception:
            log.exception("Expiry sweep failed")
        await asyncio.sleep(3600)


async def main() -> None:
    db.init_db()
    bot = Bot(token=settings.bot_token)
    dp = Dispatcher()
    dp.include_router(router)
    await _set_commands(bot)
    asyncio.create_task(_expiry_sweep(bot))
    log.info("MED VPN bot starting")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
