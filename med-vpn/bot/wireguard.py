import ipaddress
import subprocess

from config import settings
from db import used_ips


class WireGuardError(RuntimeError):
    pass


def _run(*args: str) -> str:
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        raise WireGuardError(f"{' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def generate_keypair() -> tuple[str, str]:
    """Returns (private_key, public_key)."""
    private_key = _run("wg", "genkey")
    result = subprocess.run(["wg", "pubkey"], input=private_key, capture_output=True, text=True)
    if result.returncode != 0:
        raise WireGuardError(f"wg pubkey failed: {result.stderr.strip()}")
    return private_key, result.stdout.strip()


def allocate_ip() -> str:
    network = ipaddress.ip_network(settings.wg_subnet, strict=False)
    taken = used_ips()
    hosts = network.hosts()
    next(hosts)  # skip the server's own address (first host)
    for addr in hosts:
        if str(addr) not in taken:
            return str(addr)
    raise WireGuardError("No free IP addresses left in the WireGuard subnet")


def add_peer(public_key: str, ip_address: str) -> None:
    _run("wg", "set", settings.wg_interface, "peer", public_key,
         "allowed-ips", f"{ip_address}/32")
    _run("wg-quick", "save", settings.wg_interface)


def remove_peer(public_key: str) -> None:
    _run("wg", "set", settings.wg_interface, "peer", public_key, "remove")
    _run("wg-quick", "save", settings.wg_interface)


def build_client_config(private_key: str, ip_address: str) -> str:
    return (
        "[Interface]\n"
        f"PrivateKey = {private_key}\n"
        f"Address = {ip_address}/32\n"
        f"DNS = {settings.wg_client_dns}\n"
        "\n"
        "[Peer]\n"
        f"PublicKey = {settings.wg_server_public_key}\n"
        f"Endpoint = {settings.wg_server_endpoint}\n"
        f"AllowedIPs = {settings.wg_allowed_ips}\n"
        "PersistentKeepalive = 25\n"
    )
