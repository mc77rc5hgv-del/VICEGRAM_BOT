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

    wg_interface: str = os.environ.get("WG_INTERFACE", "wg0")
    wg_conf_path: str = os.environ.get("WG_CONF_PATH", "/etc/wireguard/wg0.conf")
    wg_subnet: str = os.environ["WG_SUBNET"]              # e.g. 10.66.0.0/22
    wg_server_public_key: str = os.environ["WG_SERVER_PUBLIC_KEY"]
    wg_server_endpoint: str = os.environ["WG_SERVER_ENDPOINT"]  # host:port
    wg_client_dns: str = os.environ.get("WG_CLIENT_DNS", "1.1.1.1")
    wg_allowed_ips: str = os.environ.get("WG_ALLOWED_IPS", "0.0.0.0/0, ::/0")

    service_name: str = os.environ.get("SERVICE_NAME", "MED VPN")


settings = Settings()
