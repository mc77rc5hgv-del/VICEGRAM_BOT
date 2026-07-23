import hashlib
import secrets
import ssl
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


def _cert_pin_sha256(cert_path: str) -> str:
    pem = Path(cert_path).read_text()
    der = ssl.PEM_cert_to_DER_cert(pem)
    digest = hashlib.sha256(der).hexdigest().upper()
    return ":".join(digest[i:i + 2] for i in range(0, len(digest), 2))


def build_hysteria_uri(username: str, password: str, label: str) -> str:
    auth = f"{quote(username)}:{quote(password)}"
    pin = _cert_pin_sha256(settings.hysteria_cert_path)
    params = f"sni={quote(settings.hysteria_sni)}&pinSHA256={pin}&insecure=1"
    return f"hysteria2://{auth}@{settings.hysteria_server_endpoint}/?{params}#{quote(label)}"
