import secrets
import subprocess
from pathlib import Path
from urllib.parse import quote

import yaml

from config import settings


class HysteriaError(RuntimeError):
    pass


def generate_credentials(telegram_id: int) -> tuple[str, str]:
    username = f"tg{telegram_id}"
    password = secrets.token_urlsafe(16)
    return username, password


def _load_config() -> dict:
    return yaml.safe_load(Path(settings.hysteria_config_path).read_text())


def _save_config(cfg: dict) -> None:
    Path(settings.hysteria_config_path).write_text(yaml.dump(cfg, sort_keys=False))


def _restart_hysteria() -> None:
    result = subprocess.run(["systemctl", "restart", "hysteria-server"], capture_output=True, text=True)
    if result.returncode != 0:
        result = subprocess.run(["systemctl", "restart", "hysteria-server@config"], capture_output=True, text=True)
        if result.returncode != 0:
            raise HysteriaError(f"Failed to restart hysteria-server: {result.stderr.strip()}")


def add_user(username: str, password: str) -> None:
    cfg = _load_config()
    userpass = cfg.setdefault("auth", {}).setdefault("userpass", {})
    userpass[username] = password
    _save_config(cfg)
    _restart_hysteria()


def remove_user(username: str) -> None:
    cfg = _load_config()
    userpass = cfg.get("auth", {}).get("userpass", {})
    userpass.pop(username, None)
    _save_config(cfg)
    _restart_hysteria()


def build_hysteria_uri(username: str, password: str, label: str) -> str:
    auth = f"{quote(username)}:{quote(password)}"
    insecure = "1" if settings.hysteria_insecure else "0"
    params = f"insecure={insecure}&sni={quote(settings.hysteria_sni)}"
    return f"hysteria2://{auth}@{settings.hysteria_server_endpoint}/?{params}#{quote(label)}"
