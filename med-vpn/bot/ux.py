"""Access status never claims to observe a device's VPN connection."""
from datetime import datetime, timezone
PLATFORMS = {"android": "Android", "ios": "iPhone / iPad", "windows": "Windows", "macos": "macOS"}

def has_access(client, now=None):
    if client is None or not client.is_active:
        return False
    if not client.expires_at:
        return True
    try:
        expiry = datetime.fromisoformat(client.expires_at)
        return expiry.tzinfo is not None and expiry > (now or datetime.now(timezone.utc))
    except ValueError:
        return False

def dashboard(service_name, client):
    if has_access(client):
        until = (datetime.fromisoformat(client.expires_at).strftime("%d.%m.%Y %H:%M UTC")
                 if client.expires_at else "без ограничения срока")
        status = "🟢 Доступ активен\nСрок: " + until
        action = "Нажмите «Подключить VPN», чтобы получить вашу ссылку и QR-код."
    else:
        status = "🔴 Подписка истекла" if client and client.expires_at else "⚪ Доступ пока не активирован"
        action = "Выберите тариф или пригласите друзей. Если доступ уже оплачен — откройте поддержку."
    return service_name + "\n\n" + status + "\n\n" + action

def guide(platform):
    device = PLATFORMS.get(platform)
    if device is None:
        return None
    return ("Подключение на " + device + "\n\n"
        "1. Установите Happ из официального источника для вашего устройства.\n"
        "2. В боте нажмите «Подключить VPN» и скопируйте личную ссылку.\n"
        "3. В Happ добавьте сервер из буфера обмена или отсканируйте QR-код.\n"
        "4. Включите подключение. При первом запуске разрешите создание VPN-профиля.\n\n"
        "Статус соединения смотрите в Happ. Личную ссылку и QR-код никому не пересылайте.")
