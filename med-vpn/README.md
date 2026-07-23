# MED VPN

Self-hosted WireGuard VPN service with self-service access via a Telegram bot.
Sized for roughly 1000 users.

## Architecture

```
Telegram user  <--->  MED VPN bot (aiogram)  <--->  WireGuard (wg0) on the same VPS
                              |
                         SQLite (peers.db)
```

- **WireGuard** (`wg0`) is the VPN server itself: fast, kernel-level, minimal overhead —
  one modest VPS comfortably handles ~1000 peers.
- **The Telegram bot** runs on the same host (it needs to run `wg`/`wg-quick` as root)
  and does everything a human admin would otherwise do by hand:
  - `/getconfig` — allocates a free IP from the subnet, generates a WireGuard keypair,
    registers the peer with `wg`, and sends the user a `.conf` file + QR code.
  - `/myconfig` — resends the same config if the user needs it again.
  - `/status` — shows the user's current IP and issue date.
  - `/revoke` — lets a user disable their own access.
  - `/admin_stats`, `/admin_list`, `/admin_revoke <telegram_id>` — restricted to the IDs
    listed in `ADMIN_IDS`.
- **SQLite** stores one row per Telegram user: IP, keypair, timestamps. This lets
  `/myconfig` resend a config without asking the user to regenerate it.

## 1. Get a VPS

You don't have a server yet — for ~1000 WireGuard users, bandwidth matters far more than
CPU/RAM (WireGuard is very lightweight). Reasonable options:

| Provider | Notes |
|---|---|
| Hetzner Cloud (CX22) | Cheap, generous included traffic, good EU/US locations |
| DigitalOcean / Vultr / Linode | Simple, predictable pricing, easy snapshots |
| Contabo VPS | Cheapest bandwidth if traffic volume is high |

Minimum spec: 1 vCPU / 2 GB RAM / Ubuntu 22.04 or 24.04. Pick a datacenter region close to
your actual users.

## 2. Provision WireGuard

Copy `server/` to the VPS and run the installer as root:

```bash
scp -r server root@YOUR_SERVER_IP:/root/med-vpn-server
ssh root@YOUR_SERVER_IP
cd /root/med-vpn-server
bash install.sh
```

The script installs WireGuard, generates the server keypair, writes `/etc/wireguard/wg0.conf`,
enables IP forwarding + NAT, and starts `wg-quick@wg0`. At the end it prints the values you
need for the bot's `.env` (`WG_SERVER_PUBLIC_KEY`, `WG_SERVER_ENDPOINT`, etc).

Make sure UDP port `51820` is open in any external firewall / cloud security group too.

## 3. Deploy the bot

On the same VPS:

```bash
mkdir -p /opt/med-vpn && cp -r bot /opt/med-vpn/bot
cd /opt/med-vpn/bot
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
cp .env.example .env
# edit .env: BOT_TOKEN, ADMIN_IDS, and the WG_* values printed by install.sh
```

Get `BOT_TOKEN` from [@BotFather](https://t.me/BotFather). Get your own numeric Telegram ID
from [@userinfobot](https://t.me/userinfobot) and put it in `ADMIN_IDS`.

Run it as a systemd service:

```bash
cp /opt/med-vpn/bot/../../server/med-vpn-bot.service /etc/systemd/system/ 2>/dev/null || \
  cp server/med-vpn-bot.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now med-vpn-bot
journalctl -u med-vpn-bot -f   # check logs
```

## 4. Try it

Open your bot in Telegram and send `/start`, then `/getconfig`. You'll get a `.conf` file and
a QR code — import either into the official WireGuard app (desktop or mobile).

## Capacity notes

- The client subnet is `10.66.0.0/22` (1022 usable addresses) — enough headroom for ~1000
  users plus growth. Change `WG_SUBNET` in both `server/install.sh` and the bot's `.env`
  before first run if you want a different range.
- One VPS with a few Mbps-scale per-user usage easily serves 1000 WireGuard peers; if actual
  concurrent throughput grows much higher, scale up bandwidth/vCPU on the same box before
  considering multiple servers.

## Security notes

- `bot/med-vpn.db` contains private keys (so `/myconfig` can resend configs) — keep
  `DB_PATH` on a host-only path with restrictive permissions, back it up encrypted, and never
  commit it to git.
- `ADMIN_IDS` gates the `/admin_*` commands — double-check it before deploying.
- Consider fronting the bot token / `.env` with a secrets manager if you outgrow a single VPS.
