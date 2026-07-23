#!/usr/bin/env bash
# MED VPN — Xray-core (VLESS + Reality) server bootstrap for a fresh Ubuntu 22.04/24.04 VPS.
# Run as root: sudo bash install.sh
set -euo pipefail

XRAY_PORT="443"
XRAY_SERVER_NAME="www.microsoft.com"   # real TLS site Reality disguises the server as
XRAY_CONFIG="/usr/local/etc/xray/config.json"

if [[ $EUID -ne 0 ]]; then
  echo "Run as root (sudo bash install.sh)" >&2
  exit 1
fi

echo "==> Installing prerequisites"
apt-get update -y
apt-get install -y curl openssl

echo "==> Installing Xray-core"
bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install

echo "==> Generating Reality keypair"
KEY_OUTPUT=$(/usr/local/bin/xray x25519)
PRIVATE_KEY=$(echo "$KEY_OUTPUT" | awk -F': ' '/Private key/ {print $2}')
PUBLIC_KEY=$(echo "$KEY_OUTPUT" | awk -F': ' '/Public key/ {print $2}')
SHORT_ID=$(openssl rand -hex 8)

if [[ -z "$PRIVATE_KEY" || -z "$PUBLIC_KEY" ]]; then
  echo "Could not parse 'xray x25519' output, run it manually and fill .env by hand:" >&2
  echo "$KEY_OUTPUT" >&2
fi

echo "==> Writing $XRAY_CONFIG"
mkdir -p "$(dirname "$XRAY_CONFIG")"
cat > "$XRAY_CONFIG" <<EOF
{
  "log": { "loglevel": "warning" },
  "inbounds": [
    {
      "listen": "0.0.0.0",
      "port": $XRAY_PORT,
      "protocol": "vless",
      "settings": {
        "clients": [],
        "decryption": "none"
      },
      "streamSettings": {
        "network": "tcp",
        "security": "reality",
        "realitySettings": {
          "show": false,
          "dest": "$XRAY_SERVER_NAME:443",
          "xver": 0,
          "serverNames": ["$XRAY_SERVER_NAME"],
          "privateKey": "$PRIVATE_KEY",
          "shortIds": ["$SHORT_ID"]
        }
      },
      "sniffing": { "enabled": true, "destOverride": ["http", "tls"] }
    }
  ],
  "outbounds": [
    { "protocol": "freedom" }
  ]
}
EOF

echo "==> Starting Xray"
systemctl enable xray
systemctl restart xray

echo "==> Allow the Xray port through UFW (if present)"
if command -v ufw >/dev/null 2>&1; then
  ufw allow "${XRAY_PORT}/tcp" || true
fi

PUB_IP=$(curl -s -4 https://ifconfig.me || echo "<YOUR_SERVER_IP>")

cat <<EOF

============== MED VPN server is up (Xray / VLESS + Reality) ==============
Port:              $XRAY_PORT/tcp
Server name (SNI): $XRAY_SERVER_NAME
Public key:        $PUBLIC_KEY
Short ID:          $SHORT_ID
Server public IP:  $PUB_IP

Put these into med-vpn/bot/.env:
  XRAY_CONFIG_PATH=$XRAY_CONFIG
  XRAY_PUBLIC_KEY=$PUBLIC_KEY
  XRAY_SHORT_ID=$SHORT_ID
  XRAY_SERVER_NAME=$XRAY_SERVER_NAME
  XRAY_SERVER_ENDPOINT=$PUB_IP:$XRAY_PORT

The bot must run on THIS host as root so it can edit $XRAY_CONFIG and restart xray.
=============================================================================
EOF
