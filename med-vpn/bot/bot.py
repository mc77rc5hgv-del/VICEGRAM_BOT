import asyncio
import io
import logging

from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, Message

import db
import wireguard
from config import settings
from qr import config_to_qr_png

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("med-vpn-bot")

router = Router()


def _is_admin(telegram_id: int) -> bool:
    return telegram_id in settings.admin_ids


async def _send_config(message: Message, peer: db.Peer) -> None:
    config_text = wireguard.build_client_config(peer.private_key, peer.ip_address)
    config_file = BufferedInputFile(config_text.encode(), filename="med-vpn.conf")
    await message.answer_document(
        config_file,
        caption=(
            f"Ваш конфиг {settings.service_name} готов.\n"
            f"IP: {peer.ip_address}\n\n"
            "Импортируйте файл в приложение WireGuard или отсканируйте QR-код ниже."
        ),
    )
    qr_png = config_to_qr_png(config_text)
    await message.answer_photo(BufferedInputFile(qr_png.read(), filename="med-vpn-qr.png"))


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer(
        f"Добро пожаловать в {settings.service_name}!\n\n"
        "/getconfig — получить конфиг для подключения\n"
        "/myconfig — прислать конфиг повторно\n"
        "/status — проверить статус подключения\n"
        "/revoke — отключить свой доступ"
    )


@router.message(Command("getconfig"))
async def cmd_getconfig(message: Message) -> None:
    telegram_id = message.from_user.id
    existing = db.get_active_peer(telegram_id)
    if existing:
        await message.answer("У вас уже есть активный конфиг. Используйте /myconfig, чтобы получить его снова.")
        return

    try:
        ip_address = wireguard.allocate_ip()
        private_key, public_key = wireguard.generate_keypair()
        wireguard.add_peer(public_key, ip_address)
    except wireguard.WireGuardError as exc:
        log.exception("Failed to provision peer for %s", telegram_id)
        await message.answer(f"Не удалось создать конфиг: {exc}")
        return

    peer = db.create_peer(
        telegram_id=telegram_id,
        telegram_name=message.from_user.username,
        ip_address=ip_address,
        public_key=public_key,
        private_key=private_key,
    )
    await _send_config(message, peer)


@router.message(Command("myconfig"))
async def cmd_myconfig(message: Message) -> None:
    peer = db.get_active_peer(message.from_user.id)
    if not peer:
        await message.answer("У вас пока нет конфига. Отправьте /getconfig, чтобы получить его.")
        return
    await _send_config(message, peer)


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    peer = db.get_active_peer(message.from_user.id)
    if not peer:
        await message.answer("Доступ не активирован. Отправьте /getconfig.")
        return
    await message.answer(f"Доступ активен.\nIP: {peer.ip_address}\nВыдан: {peer.created_at}")


@router.message(Command("revoke"))
async def cmd_revoke(message: Message) -> None:
    peer = db.revoke_peer(message.from_user.id)
    if not peer:
        await message.answer("У вас нет активного конфига.")
        return
    try:
        wireguard.remove_peer(peer.public_key)
    except wireguard.WireGuardError:
        log.exception("Failed to remove peer %s from WireGuard", peer.public_key)
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
    peers = db.list_active_peers(limit=50)
    if not peers:
        await message.answer("Активных пользователей нет.")
        return
    lines = [f"{p.telegram_id} @{p.telegram_name or '-'} — {p.ip_address} ({p.created_at})" for p in peers]
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
    peer = db.revoke_peer(target_id)
    if not peer:
        await message.answer("У этого пользователя нет активного конфига.")
        return
    try:
        wireguard.remove_peer(peer.public_key)
    except wireguard.WireGuardError:
        log.exception("Failed to remove peer %s from WireGuard", peer.public_key)
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
