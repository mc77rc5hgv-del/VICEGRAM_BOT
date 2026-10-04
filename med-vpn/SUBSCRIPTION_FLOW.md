# Paid connection and menus
Connect is the single user entry: paid-access check, device selection, official Happ
downloads and instructions, then an explicit final button delivering link and QR.
Commands and old help/myconfig/getconfig buttons use the same onboarding. Successful
payments and admin-confirmed grants start onboarding instead of sending credentials early.

The final sender re-reads paid access, verifies the private destination belongs to the
client, and rejects expired/revoked/unpaid/unlimited records. Paid access requires a
future timezone-aware expiry and a positive purchase record. Stars invoices verify owner,
plan, currency and amount. Manual /admin_grant records the administrator-confirmed payment.
No subscription schema migration is needed. Existing manually issued subscriptions without
a purchase record require reconciliation with confirmed payments by an administrator.

Referrals no longer provision free accounts. Expanded menus include paying-referral count,
copy/share invitation, rules and support for manual payouts. The existing legacy balance
may aggregate currencies; it is shown as an unlabelled bookkeeping total and users are
directed to support to reconcile RUB and XTR separately. No automatic payout is implemented.
Subscription menus show Stars and RUB prices, monthly equivalent, renewal rules, recent
user-specific payments and support. Pricing and referral rates remain unchanged.

This controls NEW credential delivery in the bot. Already delivered credentials and old
free accounts on the VPN server are not revoked by this update; server removal remains an
explicit administration operation. Payment idempotency and currency-ledger migration remain
follow-up work.
