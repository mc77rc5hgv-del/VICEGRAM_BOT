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

## Subscriptions & payments

`/subscribe` (or the 💳 button) shows four plans (`bot/plans.py`), priced ~40% below the
reference service, each with a monthly-equivalent discount for longer terms:

| Plan | Price | Telegram Stars |
|---|---|---|
| 1 month | 149 ₽ | 150 ⭐ |
| 3 months | 389 ₽ | 390 ⭐ |
| 6 months | 699 ₽ | 700 ⭐ |
| 12 months | 1190 ₽ | 1190 ⭐ |

Two payment paths per plan:

- **⭐ Telegram Stars** — fully automatic via the Bot API's native payments (currency `XTR`,
  no external provider token needed). On `successful_payment` the bot provisions/extends the
  buyer's Hysteria2 access, sets `clients.expires_at`, and records the purchase (crediting
  their referrer, if any) — no admin step required.
- **💵 Rubles** — no payment gateway is wired in, so the bot instead opens a chat with
  `SUPPORT_USERNAME` (`https://t.me/<SUPPORT_USERNAME>?text=...`) pre-filled with the plan
  name and price, asking for payment details. Once you've actually received the money
  (bank transfer, SBP, crypto, however), run `/admin_grant <@username|telegram_id> <plan_key>`
  to activate their subscription and notify them — this is the same
  `_grant_subscription` path the Stars flow uses, so referral commission is credited
  identically.

Subscriptions have a real expiry (`clients.expires_at`): an hourly background sweep in
`bot.py` (`_expiry_sweep`) revokes Hysteria2 access and notifies the user once their plan
lapses. `/getconfig` (free/unlimited access, unchanged) always clears any expiry — the two
are mutually exclusive per user by design.

## Referral program

The referral system tracks attribution and commission bookkeeping, and is wired into both
subscription payment paths above:

- `/referral` (or the 💰 button) gives each user a personal link
  `https://t.me/<bot>?start=ref_<telegram_id>`. Whoever starts the bot through that link gets
  `referred_by` set once, permanently (re-using the link, or any other referral link, later
  never overwrites it).
- `/admin_purchase <telegram_id> <amount> [currency]` — admin-only. Records a purchase and,
  if the buyer has a referrer, credits them `REFERRAL_COMMISSION_RATE` (default 10%) of the
  amount to their balance. Use this manually today (e.g. after receiving a crypto/bank
  payment outside the bot); once a real payment gateway is added, its webhook should call
  `db.record_purchase(...)` directly instead.
- `/admin_payout <telegram_id>` — admin-only. Zeroes out a referrer's balance once you've
  actually sent them their commission (bank transfer, crypto, etc. — payout itself is manual,
  this just marks it done).
- Users see their invite count and balance via `/referral`.

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

## Deploying updates

The bot on the server runs from a direct git checkout (not a copied folder), authenticated
via a read-only SSH deploy key added to this repo. This means every future code change is
one command on the server — no more copying files by hand:

```bash
cd /opt/vicegram-bot-src && git pull && systemctl restart med-vpn-bot
```

If `requirements.txt` changed, also run
`./med-vpn/bot/venv/bin/pip install -r med-vpn/bot/requirements.txt` before restarting.

One-time setup for a new server (already done for the current one):

```bash
ssh-keygen -t ed25519 -f ~/.ssh/medvpn_deploy -N "" -C "medvpn-server-deploy"
cat ~/.ssh/medvpn_deploy.pub   # add as a read-only Deploy Key on the GitHub repo
printf '%s\n' 'Host github.com' '  IdentityFile ~/.ssh/medvpn_deploy' '  IdentitiesOnly yes' > ~/.ssh/config
chmod 600 ~/.ssh/config
ssh-keyscan -t ed25519 github.com >> ~/.ssh/known_hosts
git clone --branch <branch> git@github.com:mc77rc5hgv-del/VICEGRAM_BOT.git /opt/vicegram-bot-src
cp <old .env> /opt/vicegram-bot-src/med-vpn/bot/.env
cd /opt/vicegram-bot-src/med-vpn/bot && python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
```

Then point `med-vpn-bot.service`'s `WorkingDirectory`, `EnvironmentFile`, and `ExecStart` at
`/opt/vicegram-bot-src/med-vpn/bot/...` and `systemctl daemon-reload`.

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
- The self-signed certificate is pinned in each client link via `pinSHA256` (computed from
  `/etc/hysteria/cert.pem`), so clients verify the exact certificate instead of skipping
  validation outright — this also avoids the "allow-Insecure has been removed" crash some
  Xray-core-based clients (incl. some Happ versions) raise on plain `insecure=1` links.
  If the server certificate is ever regenerated, every issued link becomes invalid since the
  pin changes — reissue links with `/getconfig` after that.
