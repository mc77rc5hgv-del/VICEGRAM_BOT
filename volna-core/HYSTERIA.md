# Managed Hysteria2 compatibility adapter (Unix)

HysteriaConnector implements SmartConnect using an owned Hysteria2 subprocess
and an authenticated local SOCKS5 proxy. No shell is invoked. The supplied absolute
executable must be provisioned from a verified release by the platform owner.
CI pins v2.12.3 linux-amd64 and verifies its published SHA256 before execution.

Inputs: route ID, server IP:port, username/password, SNI and mandatory certificate
SHA256. JSON config is created in a private temporary directory with mode 0600.
Credentials are not argv arguments or inherited environment variables; raw
subprocess output is suppressed. Secrets remain in process memory and the
temporary file while connected; this is not an encrypted credential vault.

TLS uses mandatory leaf DER certificate pin verification. Hysteria's
insecure=true disables CA/name checks for compatibility with current self-signed
Med VPN certificates, but pinSHA256 still verifies the exact leaf. Empty or
malformed pins are rejected; there is no unpinned mode. Pin-only trust means
certificate expiry/SNI validation is not enforced. Distribution and rotation
of pins must use the future signed manifest.

Random SOCKS credentials isolate local sessions. A port reservation is released
immediately before spawn; if another process steals it, authentication prevents
false readiness (failure is still possible). Each readiness check requires
HTTPS 204 through the owned proxy; TLS at the health service is separately verified.
This is a working HTTP-over-Hysteria/QUIC path, not whole-device IP protection.

Normal shutdown kills and awaits the child. Dropping or cancelling a race uses
Tokio kill_on_drop and its reaper; termination is requested synchronously but
completion is eventual. Dropping the session deletes its temp config. The runtime
must stay alive long enough to reap killed children. No detached child work is
started. Platform owner must treat a dead process/failed probes as connection loss.

The local integration fixture starts a real Hysteria2 server and managed Rust
client, sends HTTPS payload through QUIC, rejects bad userpass and certificate
pins, checks explicit shutdown, drop cleanup and network-generation cancellation.
It does not use production servers, accounts or keys.

Remaining: Windows/mobile process model, protected sockets on Android, TUN/IP,
UDP/DNS/IPv6 checks, continuous health and migration activation. Hysteria2 is
a compatibility bridge; it does not replace planned AWG/MASQUE/TCP transports.
