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

    hysteria_config_path: str = os.environ.get("HYSTERIA_CONFIG_PATH", "/etc/hysteria/config.yaml")
    hysteria_server_endpoint: str = os.environ["HYSTERIA_SERVER_ENDPOINT"]  # host:port, e.g. 1.2.3.4:443
    hysteria_sni: str = os.environ.get("HYSTERIA_SNI", "med-vpn.internal")
    hysteria_insecure: bool = os.environ.get("HYSTERIA_INSECURE", "1") == "1"

    service_name: str = os.environ.get("SERVICE_NAME", "MED VPN")


settings = Settings()
