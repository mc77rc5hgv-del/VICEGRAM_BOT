#!/usr/bin/env bash
# MED VPN — WireGuard server bootstrap for a fresh Ubuntu 22.04/24.04 VPS.
# Run as root: sudo bash install.sh
set -euo pipefail

WG_IFACE="wg0"
WG_PORT="51820"
WG_SUBNET="10.66.0.0/22"      # ~1000 usable client addresses
WG_SERVER_IP="10.66.0.1/22"
WG_DIR="/etc/wireguard"

if [[ $EUID -ne 0 ]]; then
  echo "Run as root (sudo bash install.sh)" >&2
  exit 1
fi

echo "==> Installing packages"
apt-get update -y
apt-get install -y wireguard wireguard-tools qrencode iptables-persistent

echo "==> Generating server keys"
umask 077
mkdir -p "$WG_DIR"
if [[ ! -f "$WG_DIR/server_private.key" ]]; then
  wg genkey | tee "$WG_DIR/server_private.key" | wg pubkey > "$WG_DIR/server_public.key"
fi
SERVER_PRIV=$(cat "$WG_DIR/server_private.key")

PUB_IF=$(ip route show default | awk '/default/ {print $5; exit}')
if [[ -z "$PUB_IF" ]]; then
  echo "Could not detect the public network interface, edit $WG_DIR/$WG_IFACE.conf manually." >&2
  PUB_IF="eth0"
fi

echo "==> Writing $WG_DIR/$WG_IFACE.conf"
cat > "$WG_DIR/$WG_IFACE.conf" <<EOF
[Interface]
Address = $WG_SERVER_IP
ListenPort = $WG_PORT
PrivateKey = $SERVER_PRIV
PostUp = iptables -A FORWARD -i %i -j ACCEPT; iptables -t nat -A POSTROUTING -o $PUB_IF -j MASQUERADE
PostDown = iptables -D FORWARD -i %i -j ACCEPT; iptables -t nat -D POSTROUTING -o $PUB_IF -j MASQUERADE
SaveConfig = true

# Peers are appended below by the MED VPN bot (wg-quick save $WG_IFACE)
EOF
chmod 600 "$WG_DIR/$WG_IFACE.conf"

echo "==> Enabling IP forwarding"
cat > /etc/sysctl.d/99-med-vpn.conf <<EOF
net.ipv4.ip_forward = 1
EOF
sysctl --system > /dev/null

echo "==> Starting WireGuard"
systemctl enable --now "wg-quick@${WG_IFACE}"

echo "==> Allow the WireGuard port through UFW (if present)"
if command -v ufw >/dev/null 2>&1; then
  ufw allow "${WG_PORT}/udp" || true
fi

SERVER_PUB=$(cat "$WG_DIR/server_public.key")
PUB_IP=$(curl -s -4 https://ifconfig.me || echo "<YOUR_SERVER_IP>")

cat <<EOF

==================== MED VPN server is up ====================
Interface:        $WG_IFACE
Listen port:      $WG_PORT/udp
Client subnet:    $WG_SUBNET
Server public IP: $PUB_IP
Server pubkey:    $SERVER_PUB

Put these into med-vpn/bot/.env:
  WG_INTERFACE=$WG_IFACE
  WG_CONF_PATH=$WG_DIR/$WG_IFACE.conf
  WG_SERVER_PUBLIC_KEY=$SERVER_PUB
  WG_SERVER_ENDPOINT=$PUB_IP:$WG_PORT
  WG_SUBNET=$WG_SUBNET

The bot must run on THIS host as root (or via sudo) so it can call `wg`/`wg-quick`.
================================================================
EOF
