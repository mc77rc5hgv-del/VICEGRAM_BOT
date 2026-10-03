# Application data-path supervisor

supervise owns active, prewarming and ready backup sessions. MonitoredConnector
provides fresh end-to-end probes and a clonable application request handle.
Hysteria's probe checks process liveness and HTTPS 204 through authenticated SOCKS,
measuring request elapsed time. This is not packet-loss, jitter or throughput telemetry.

Sustained high probe time or the first failed probe triggers prewarm in an independent
configured failure domain. A fresh backup probe is required before switching.
Consecutive failures permit recovery; high latency requires a measurable improvement
and cooldown. Backup lifetime is bounded; failures retry with exponential backoff.
Recovery cancels unnecessary prewarm. Watch channels publish status and the handle
for new application requests. Drop/epoch cancellation clear publication and drop sessions.

supervise preserves application-only behavior. supervise_with_activation accepts
an owned platform activation hook. Activation must succeed before Connected is
published, both initially and on failover; the old session remains alive until
activation and publication finish. Activation failure returns Activation and clears
publication while dropping sessions. A Linux HysteriaTunActivator connects this
hook to LinuxPolicyRouter. Cancellation never implicitly calls disconnect.

Switching publishes a new handle before dropping the old session. Requests already
using the old proxy can fail: no TCP-flow preservation, arbitrary request replay,
existing-flow migration or mobile network migration is implemented. Linux route
activation and fail-closed guards are opt-in and have the limits documented in TUN.md.
Route config is a snapshot for the supervisor lifetime; changed signed manifests
must invalidate the epoch and restart the supervisor. A failed active route with no
usable reserve ends in Failed, not a claim of physical NoConnectivity.

Probe and race deadlines bound network work; skipped timer ticks prevent catch-up
bursts. Thresholds are initial policy values requiring real network tuning. Health
runs continuously on a worker runtime. TLS/proxy ownership contracts still apply.

CI tests virtual-time prewarm/switch, rejected reserves and cancellation. A real
two-edge Hysteria2 fixture prepares a backup, stops the primary QUIC server, verifies
publication switches to the backup and reads payload through that path. Both test
edges are on loopback; their distinct failure-domain labels are synthetic.
