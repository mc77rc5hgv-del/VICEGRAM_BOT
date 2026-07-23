# MED VPN

Self-hosted VLESS + Reality (Xray-core) VPN service with self-service access via a
Telegram bot. Clients connect using the **Happ** app. Sized for ~200 users.

## Architecture

```
Telegram user  <--->  MED VPN bot (aiogram)  <--->  Xray-core (VLESS+Reality) on the same VPS
                              |
                         SQLite (clients.db)
```

- **Xray-core** runs a VLESS inbound with **Reality**, which disguises the VPN handshake as
  normal HTTPS traffic to a real website (`XRAY_SERVER_NAME`) — this is what makes it far
  harder for DPI-based blocking to detect and block than WireGuard/OpenVPN.
- **The Telegram bot** runs on the same host (it edits `/usr/local/etc/xray/config.json` and
  restarts the `xray` service, so it needs root) and does everything a human admin would
  otherwise do by hand:
  - `/getconfig` — generates a UUID, adds it as a client in the Xray config, and sends the
    user a `vless://...` link + QR code to import into **Happ**.
  - `/myconfig` — resends the same link.
  - `/status` — shows when access was issued.
  - `/revoke` — lets a user disable their own access.
  - `/admin_stats`, `/admin_list`, `/admin_revoke <telegram_id>` — restricted to the IDs
    listed in `ADMIN_IDS`.
- **SQLite** stores one row per Telegram user: UUID + timestamps, so `/myconfig` can resend
  the same link without regenerating it.

## 1. Get a VPS

Any VPS outside Russia works (Netherlands, Germany, etc. — see the hosting notes from
earlier in this project). Minimum spec: 1 vCPU / 1-2 GB RAM / Ubuntu 22.04 or 24.04 —
comfortably handles ~200 users.

## 2. Provision Xray (VLESS + Reality)

Copy `server/` to the VPS and run the installer as root:

```bash
scp -r server root@YOUR_SERVER_IP:/root/med-vpn-server
ssh root@YOUR_SERVER_IP
cd /root/med-vpn-server
bash install.sh
```

The script installs Xray-core (via the official XTLS installer), generates the Reality
keypair + a short ID, writes `/usr/local/etc/xray/config.json` with an empty client list,
and starts the `xray` service on port 443/tcp. At the end it prints the values you need for
the bot's `.env` (`XRAY_PUBLIC_KEY`, `XRAY_SHORT_ID`, `XRAY_SERVER_ENDPOINT`, etc).

Make sure TCP port `443` is open in any external firewall / cloud security group.

`XRAY_SERVER_NAME` defaults to `www.microsoft.com` (the site Reality "impersonates"). You
can change it in `server/install.sh` before running it if you prefer a different one — pick
a real, popular site that serves TLS 1.3 on port 443.

## 3. Deploy the bot

On the same VPS:

```bash
mkdir -p /opt/med-vpn && cp -r bot /opt/med-vpn/bot
cd /opt/med-vpn/bot
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
cp .env.example .env
# edit .env: BOT_TOKEN, ADMIN_IDS, and the XRAY_* values printed by install.sh
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

Open your bot in Telegram and send `/start`, then `/getconfig`. You'll get a `vless://...`
link and a QR code. In **Happ**: Add server → "Add from clipboard" (paste the link) or scan
the QR code directly.

## Capacity notes

- Each user only needs a UUID (no IP pool, unlike WireGuard) — thousands of clients can
  share the same Reality keypair/short ID, so there's no practical ceiling at ~200 users.
- Every `/getconfig`, `/revoke`, or `/admin_revoke` restarts the `xray` process to apply the
  new client list — this takes well under a second and briefly interrupts other connected
  users' streams, which is a non-issue at this scale.

## Security notes

- `bot/med-vpn.db` only stores UUIDs (no private keys), but still keep `DB_PATH` on a
  host-only path with restrictive permissions and never commit it to git.
- `ADMIN_IDS` gates the `/admin_*` commands — double-check it before deploying.
- The Reality private key lives only in `/usr/local/etc/xray/config.json` on the server —
  never share it; only the public key goes to clients.
