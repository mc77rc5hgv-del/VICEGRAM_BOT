#!/usr/bin/env bash
# MED VPN — Hysteria2 server bootstrap for a fresh Ubuntu 22.04/24.04 VPS.
# Hysteria2 runs over UDP/QUIC, which currently passes Russian DPI (TSPU)
# much more reliably than TCP-based VLESS+Reality.
# Run as root: sudo bash install.sh
set -euo pipefail

HYSTERIA_PORT="443"
HYSTERIA_CONFIG="/etc/hysteria/config.yaml"
HYSTERIA_SNI="med-vpn.internal"
MASQUERADE_URL="https://news.ycombinator.com"

if [[ $EUID -ne 0 ]]; then
  echo "Run as root (sudo bash install.sh)" >&2
  exit 1
fi

echo "==> Installing prerequisites"
apt-get update -y
apt-get install -y curl openssl

echo "==> Installing Hysteria2"
bash <(curl -fsSL https://get.hy2.sh/)

echo "==> Generating self-signed TLS certificate"
mkdir -p /etc/hysteria
openssl req -x509 -nodes -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 \
  -keyout /etc/hysteria/key.pem -out /etc/hysteria/cert.pem \
  -subj "/CN=$HYSTERIA_SNI" -days 3650
chown hysteria:hysteria /etc/hysteria/key.pem /etc/hysteria/cert.pem 2>/dev/null || true

echo "==> Writing $HYSTERIA_CONFIG"
cat > "$HYSTERIA_CONFIG" <<EOF
listen: :$HYSTERIA_PORT

tls:
  cert: /etc/hysteria/cert.pem
  key: /etc/hysteria/key.pem

auth:
  type: userpass
  userpass: {}

masquerade:
  type: proxy
  proxy:
    url: $MASQUERADE_URL
    rewriteHost: true
EOF

echo "==> Stopping any previous Xray setup (MED VPN now uses Hysteria2)"
systemctl disable --now xray 2>/dev/null || true

echo "==> Starting Hysteria2"
systemctl enable hysteria-server.service 2>/dev/null || systemctl enable hysteria-server@config.service
systemctl restart hysteria-server.service 2>/dev/null || systemctl restart hysteria-server@config.service
sleep 1
STATUS=$(systemctl is-active hysteria-server.service 2>/dev/null || systemctl is-active hysteria-server@config.service 2>/dev/null || echo "unknown")

echo "==> Allow the Hysteria2 port through UFW (if present)"
if command -v ufw >/dev/null 2>&1; then
  ufw allow "${HYSTERIA_PORT}/udp" || true
fi

PUB_IP=$(curl -s -4 https://ifconfig.me || echo "<YOUR_SERVER_IP>")

cat <<EOF

============== MED VPN server is up (Hysteria2) ==============
Service status:    $STATUS
Port:              $HYSTERIA_PORT/udp
SNI:               $HYSTERIA_SNI
Server public IP:  $PUB_IP

Put these into med-vpn/bot/.env:
  HYSTERIA_CONFIG_PATH=$HYSTERIA_CONFIG
  HYSTERIA_SERVER_ENDPOINT=$PUB_IP:$HYSTERIA_PORT
  HYSTERIA_SNI=$HYSTERIA_SNI
  HYSTERIA_INSECURE=1

The bot must run on THIS host as root so it can edit $HYSTERIA_CONFIG and restart hysteria-server.
=================================================================
EOF
