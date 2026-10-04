"""Access status never claims to observe a device's VPN connection."""
from datetime import datetime, timezone
PLATFORMS = {"android": "Android", "ios": "iPhone / iPad", "windows": "Windows", "macos": "macOS"}

# Official Happ download links, published in Happ-proxy/happ-desktop README.
HAPP_DOWNLOADS = {
    "android": (
        ("Google Play", "https://play.google.com/store/apps/details?id=com.happproxy"),
        ("Скачать APK", "https://github.com/Happ-proxy/happ-android/releases/latest/download/Happ.apk"),
    ),
    "ios": (
        ("App Store", "https://apps.apple.com/us/app/happ-proxy-utility/id6504287215"),
        ("App Store РФ — Happ Lite", "https://apps.apple.com/ru/app/happ-lite/id6799917773"),
    ),
    "windows": (
        ("Скачать для Windows x64", "https://github.com/Happ-proxy/happ-desktop/releases/latest/download/setup-Happ.x64.exe"),
        ("Скачать для Windows ARM64", "https://github.com/Happ-proxy/happ-desktop/releases/latest/download/setup-Happ.arm64.exe"),
    ),
    "macos": (
        ("Скачать для Mac — Intel / Apple Silicon", "https://github.com/Happ-proxy/happ-desktop/releases/latest/download/Happ.macOS.universal.dmg"),
    ),
}

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
    notes = {
        "android": "Если Google Play недоступен, используйте официальный APK.\n\n",
        "ios": "Для российского App Store доступна отдельная версия Happ Lite.\n\n",
        "windows": "Для большинства ПК выберите x64. Для Windows на ARM — ARM64.\n\n",
        "macos": "Один установщик подходит для Mac с Intel и Apple Silicon.\n\n",
    }
    return ("Подключение на " + device + "\n\n" + notes[platform]
        "1. Скачайте Happ по кнопке ниже и установите приложение.\n"
        "2. В боте нажмите «Подключить VPN» и скопируйте личную ссылку.\n"
        "3. В Happ добавьте сервер из буфера обмена или отсканируйте QR-код.\n"
        "4. Включите подключение. При первом запуске разрешите создание VPN-профиля.\n\n"
        "Статус соединения смотрите в Happ. Личную ссылку и QR-код никому не пересылайте.")
