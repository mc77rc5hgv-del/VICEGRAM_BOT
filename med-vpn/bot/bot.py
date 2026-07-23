import asyncio
import logging

from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, Message

import db
import xray_backend as xray
from config import settings
from qr import config_to_qr_png

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("med-vpn-bot")

router = Router()


def _is_admin(telegram_id: int) -> bool:
    return telegram_id in settings.admin_ids


async def _send_config(message: Message, client: db.Client) -> None:
    label = f"tg{client.telegram_id}"
    vless_uri = xray.build_vless_uri(client.uuid, label)
    await message.answer(
        f"Ваша ссылка {settings.service_name} готова.\n\n"
        f"`{vless_uri}`\n\n"
        "Откройте приложение Happ, вставьте ссылку (Добавить сервер → Из буфера обмена) "
        "или отсканируйте QR-код ниже.",
        parse_mode="Markdown",
    )
    qr_png = config_to_qr_png(vless_uri)
    await message.answer_photo(BufferedInputFile(qr_png.read(), filename="med-vpn-qr.png"))


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer(
        f"Добро пожаловать в {settings.service_name}!\n\n"
        "/getconfig — получить ссылку для подключения (Happ)\n"
        "/myconfig — прислать ссылку повторно\n"
        "/status — проверить статус подключения\n"
        "/revoke — отключить свой доступ"
    )


@router.message(Command("getconfig"))
async def cmd_getconfig(message: Message) -> None:
    telegram_id = message.from_user.id
    existing = db.get_active_client(telegram_id)
    if existing:
        await message.answer("У вас уже есть активная ссылка. Используйте /myconfig, чтобы получить её снова.")
        return

    client_uuid = xray.generate_uuid()
    label = f"tg{telegram_id}"
    try:
        xray.add_client(client_uuid, label)
    except xray.XrayError as exc:
        log.exception("Failed to provision client for %s", telegram_id)
        await message.answer(f"Не удалось создать ссылку: {exc}")
        return

    client = db.create_client(
        telegram_id=telegram_id,
        telegram_name=message.from_user.username,
        client_uuid=client_uuid,
    )
    await _send_config(message, client)


@router.message(Command("myconfig"))
async def cmd_myconfig(message: Message) -> None:
    client = db.get_active_client(message.from_user.id)
    if not client:
        await message.answer("У вас пока нет ссылки. Отправьте /getconfig, чтобы получить её.")
        return
    await _send_config(message, client)


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    client = db.get_active_client(message.from_user.id)
    if not client:
        await message.answer("Доступ не активирован. Отправьте /getconfig.")
        return
    await message.answer(f"Доступ активен.\nВыдан: {client.created_at}")


@router.message(Command("revoke"))
async def cmd_revoke(message: Message) -> None:
    client = db.revoke_client(message.from_user.id)
    if not client:
        await message.answer("У вас нет активной ссылки.")
        return
    try:
        xray.remove_client(client.uuid)
    except xray.XrayError:
        log.exception("Failed to remove client %s from Xray", client.uuid)
    await message.answer("Доступ отключён. Чтобы подключиться снова, отправьте /getconfig.")


@router.message(Command("admin_stats"))
async def cmd_admin_stats(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return
    s = db.stats()
    await message.answer(f"Активных пользователей: {s['active']}\nОтозвано: {s['revoked']}")


@router.message(Command("admin_list"))
async def cmd_admin_list(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return
    clients = db.list_active_clients(limit=50)
    if not clients:
        await message.answer("Активных пользователей нет.")
        return
    lines = [f"{c.telegram_id} @{c.telegram_name or '-'} — {c.created_at}" for c in clients]
    await message.answer("\n".join(lines))


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
        xray.remove_client(client.uuid)
    except xray.XrayError:
        log.exception("Failed to remove client %s from Xray", client.uuid)
    await message.answer(f"Доступ пользователя {target_id} отозван.")


async def main() -> None:
    db.init_db()
    bot = Bot(token=settings.bot_token)
    dp = Dispatcher()
    dp.include_router(router)
    log.info("MED VPN bot starting")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
