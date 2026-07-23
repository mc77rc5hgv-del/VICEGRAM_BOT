# MED VPN

Self-hosted Hysteria2 VPN service with self-service access via a Telegram bot. Clients
connect using the **Happ** app. Sized for ~200 users.

## Why Hysteria2

The project started on WireGuard, moved to VLESS+Reality (for Happ compatibility), and as
of mid-2026 moved again to **Hysteria2** after Russian DPI (RKN's ТСПУ) started actively
cutting the TCP handshake of plain VLESS+TCP+Reality connections. Hysteria2 runs over
UDP/QUIC, which the current generation of DPI equipment handles far less aggressively than
TCP — this is also what most commercial VPN apps (Happ's own bundled options, other
providers) have converged on for Russian users.

## Architecture

```
Telegram user  <--->  MED VPN bot (aiogram)  <--->  Hysteria2 (UDP/443) on the same VPS
                              |
                         SQLite (clients.db)
```

- **Hysteria2** runs a UDP listener with a self-signed TLS certificate and per-user
  `userpass` authentication (username/password pairs in `/etc/hysteria/config.yaml`).
- **The Telegram bot** runs on the same host (it edits `config.yaml` and restarts the
  `hysteria-server` service, so it needs root):
  - `/getconfig` — generates a username/password, adds it to the Hysteria2 config, and
    sends the user a `hysteria2://...` link + QR code to import into **Happ**.
  - `/myconfig` — resends the same link.
  - `/status` — shows when access was issued.
  - `/revoke` — lets a user disable their own access.
  - `/admin_stats`, `/admin_list`, `/admin_revoke <telegram_id>` — restricted to the IDs
    listed in `ADMIN_IDS`.
- **SQLite** stores one row per Telegram user: username + password + timestamps, so
  `/myconfig` can resend the same link without regenerating it.

## 1. Get a VPS

Any VPS outside Russia works (Netherlands, Germany, etc). Minimum spec: 1 vCPU / 1-2 GB
RAM / Ubuntu 22.04 or 24.04 — comfortably handles ~200 users.

## 2. Provision Hysteria2

Copy `server/` to the VPS and run the installer as root:

```bash
scp -r server root@YOUR_SERVER_IP:/root/med-vpn-server
ssh root@YOUR_SERVER_IP
cd /root/med-vpn-server
bash install.sh
```

The script installs Hysteria2 (via the official get.hy2.sh installer), generates a
self-signed TLS certificate, writes `/etc/hysteria/config.yaml` with an empty user list,
and starts the `hysteria-server` service on UDP/443. It also disables any leftover Xray
service from a previous version of this project. At the end it prints the values you need
for the bot's `.env`.

Make sure **UDP** port `443` is open in any external firewall / cloud security group.

## 3. Deploy the bot

On the same VPS:

```bash
mkdir -p /opt/med-vpn && cp -r bot /opt/med-vpn/bot
cd /opt/med-vpn/bot
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
cp .env.example .env
# edit .env: BOT_TOKEN, ADMIN_IDS, and the HYSTERIA_* values printed by install.sh
```

Get `BOT_TOKEN` from [@BotFather](https://t.me/BotFather). Get your own numeric Telegram ID
from [@userinfobot](https://t.me/userinfobot) and put it in `ADMIN_IDS`.

Run it as a systemd service:

```bash
cp server/med-vpn-bot.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now med-vpn-bot
journalctl -u med-vpn-bot -f   # check logs
```

## 4. Try it

Open your bot in Telegram and send `/start`, then `/getconfig`. You'll get a
`hysteria2://...` link and a QR code. In **Happ**: Add server → "Add from clipboard" (paste
the link) or scan the QR code directly.

## Capacity notes

- Each user only needs a username/password pair — no IP pool or per-user keypair, so there's
  no practical ceiling at ~200 users.
- Every `/getconfig`, `/revoke`, or `/admin_revoke` restarts `hysteria-server` to apply the
  new user list — this takes under a second and briefly interrupts other connected users,
  which is a non-issue at this scale.

## Security notes

- `bot/med-vpn.db` stores plaintext passwords (needed so `/myconfig` can resend the same
  credentials) — keep `DB_PATH` on a host-only path with restrictive permissions and never
  commit it to git.
- `ADMIN_IDS` gates the `/admin_*` commands — double-check it before deploying.
- The self-signed certificate means clients connect with `insecure=1` (no CA chain
  validation) — acceptable for a small private VPN, since the client already trusts the
  server via its username/password, but be aware it doesn't protect against an
  on-path attacker impersonating the server the very first time a client connects.
