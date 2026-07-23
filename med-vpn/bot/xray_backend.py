import json
import subprocess
import uuid as uuid_lib
from pathlib import Path
from urllib.parse import quote

from config import settings


class XrayError(RuntimeError):
    pass


def generate_uuid() -> str:
    return str(uuid_lib.uuid4())


def _load_config() -> dict:
    return json.loads(Path(settings.xray_config_path).read_text())


def _save_config(cfg: dict) -> None:
    Path(settings.xray_config_path).write_text(json.dumps(cfg, indent=2))


def _vless_inbound(cfg: dict) -> dict:
    for inbound in cfg.get("inbounds", []):
        if inbound.get("protocol") == "vless":
            return inbound
    raise XrayError("No VLESS inbound found in Xray config")


def _restart_xray() -> None:
    result = subprocess.run(["systemctl", "restart", "xray"], capture_output=True, text=True)
    if result.returncode != 0:
        raise XrayError(f"Failed to restart xray: {result.stderr.strip()}")


def add_client(client_uuid: str, label: str) -> None:
    cfg = _load_config()
    inbound = _vless_inbound(cfg)
    clients = inbound["settings"].setdefault("clients", [])
    clients.append({"id": client_uuid, "email": label, "flow": "xtls-rprx-vision"})
    _save_config(cfg)
    _restart_xray()


def remove_client(client_uuid: str) -> None:
    cfg = _load_config()
    inbound = _vless_inbound(cfg)
    clients = inbound["settings"].get("clients", [])
    inbound["settings"]["clients"] = [c for c in clients if c["id"] != client_uuid]
    _save_config(cfg)
    _restart_xray()


def build_vless_uri(client_uuid: str, label: str) -> str:
    params = (
        "security=reality&encryption=none"
        f"&pbk={settings.xray_public_key}"
        "&fp=chrome"
        f"&sni={settings.xray_server_name}"
        f"&sid={settings.xray_short_id}"
        "&type=tcp&flow=xtls-rprx-vision"
    )
    return f"vless://{client_uuid}@{settings.xray_server_endpoint}?{params}#{quote(label)}"
