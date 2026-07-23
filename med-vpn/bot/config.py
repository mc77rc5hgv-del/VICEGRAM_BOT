import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _split_ids(raw: str) -> set[int]:
    return {int(x) for x in raw.replace(",", " ").split() if x.strip()}


@dataclass(frozen=True)
class Settings:
    bot_token: str = os.environ["BOT_TOKEN"]
    admin_ids: set[int] = field(default_factory=lambda: _split_ids(os.environ.get("ADMIN_IDS", "")))

    db_path: str = os.environ.get("DB_PATH", "/etc/med-vpn/med-vpn.db")

    xray_config_path: str = os.environ.get("XRAY_CONFIG_PATH", "/usr/local/etc/xray/config.json")
    xray_public_key: str = os.environ["XRAY_PUBLIC_KEY"]
    xray_short_id: str = os.environ["XRAY_SHORT_ID"]
    xray_server_name: str = os.environ.get("XRAY_SERVER_NAME", "www.microsoft.com")
    xray_server_endpoint: str = os.environ["XRAY_SERVER_ENDPOINT"]  # host:port, e.g. 1.2.3.4:443

    service_name: str = os.environ.get("SERVICE_NAME", "MED VPN")


settings = Settings()
