# Bot navigation release
The start screen now shows access state and its expiry, a primary Connect action,
renewal, device guides and support. /connect and /getconfig reuse the same access
path as the Connect button. Existing credentials are resent without regeneration.
Expired subscriptions are not presented as active while awaiting the hourly sweep.
Disconnect/revoke is available in the account screen with the existing confirmation.

Copy buttons are used only for links of at most 256 characters; longer links remain
selectable in the message and importable by QR. Links use escaped HTML.
Navigation screens edit the current message. Credentials are sent separately.
Account handlers are restricted to private chats. Prices and payment logic are unchanged.

## Existing VPS update
The documented production setup uses /opt/vicegram-bot-src and med-vpn-bot.service.
After the release has been merged into the checked-out VPN branch, take the normal
database/config backup, then update the checkout and its existing virtual environment:

    cd /opt/vicegram-bot-src
    git pull --ff-only
    ./med-vpn/bot/venv/bin/pip install -r med-vpn/bot/requirements.txt
    systemctl restart med-vpn-bot
    systemctl is-active med-vpn-bot

Do not run the provisioning installer for an update; it can replace server configuration.
Check /start, existing-user /connect, instructions, renewal and support using a private
test account. Check runtime logs for polling conflicts or errors without publishing
tokens, passwords or config URIs. Retain the previous commit and environment for rollback.

## Scope
This release improves the existing Happ-based bot. The Rust core is client-side and
is not loaded by Happ or this bot; merging its source is not distribution to users.
Native VOLNA clients, mobile integration and production VPN-edge rollout remain separate.
