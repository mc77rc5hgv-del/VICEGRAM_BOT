# Hysteria2 compatibility data path

SocksConnector joins SmartConnect to loopback SOCKS5 proxies run by a separately
supervised Hysteria2 client. Each route ID maps to its own proxy. Existing production
server and credentials are unchanged. This is an HTTP data path, not raw IP or TUN.

The adapter requests an operator-controlled HTTPS health endpoint expecting 204,
with TLS verification, no redirects, no environment proxy inheritance or direct
fallback. socks5h sends domain names to the proxy for remote resolution.
Errors are coarse and never include credentials or response bodies.

The local proxy must be exclusively owned by the trusted platform supervisor.
The adapter cannot establish which software owns a port or verify Hysteria's
upstream pin/authentication. Provisioning must supply Hysteria2 endpoint, userpass,
SNI and certificate pin; only the existing external client currently does this.
Do not advertise CONNECTED/PROTECTED based on this adapter: it verifies HTTPS
reachability only; DNS, UDP, IPv6 and IP routing remain unverified.

Dropping a session closes its reqwest connection resources; it does not stop the
external Hysteria process. Standby proxy lifecycle belongs to the supervisor.
Android must supply protected outbound sockets to prevent routing loops.

CI runs a real local TLS origin behind a SOCKS5 relay, verifies proxied response
bytes, rejects an untrusted certificate, and rejects a dead proxy while the
origin remains reachable. The relay insists on domain-name addressing.
This validates the SOCKS integration, not the actual Hysteria2 QUIC protocol.

Run: python3 volna-core/tests/socks_fixture.py
Next: managed Hysteria2 lifecycle, credentials/pin config, real Hysteria client/server
fixture, then platform TUN integration and complete IP/DNS leak tests.
