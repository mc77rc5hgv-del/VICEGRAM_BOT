# Linux TUN prototype
Hysteria2 native TUN carries ordinary TCP and UDP packets. Optional per-route
profiles create distinct interfaces and addresses; automatic routing is disabled.
QUIC sockets carry mark 0x564f and bypass the VPN policy table.

LinuxPolicyRouter requires root and a trusted absolute iproute2 path. The platform
must reserve a routing table and two priorities and provide a single controller.
Existing entries are rejected. Blackhole defaults remain when a session or controller
dies. Explicit disconnect removes guards and restores ordinary routing.
Local destinations still follow the kernel local table. Earlier policy rules,
other privileged controllers and concurrent routing changes are outside this
prototype's ownership model. Dual-stack route updates are sequential.

The isolated namespace fixture checks ordinary HTTPS and UDP through TUN,
automatic failover after primary QUIC server loss, actual reserve kernel routes,
direct-traffic blocking before activation, blocking after cancellation and restoration
after explicit disconnect. It never changes the host default route. The binary
release and certificate pin are verified.

supervise_with_activation now uses HysteriaTunActivator to install the selected
session's routes before Connected publication and before dropping the old session.
Fresh reserve health validation precedes activation. An activation error fails the
supervisor and closes its sessions while retaining routing guards; it does not
claim Connected or implicitly restore direct access. Epoch cancellation waits for
in-flight activation completion, then clears publication and closes sessions.
The caller retains router ownership and must explicitly disconnect to restore
ordinary routing. Hard task abortion can still interrupt sequential platform work.
Android VpnService,
DNS ownership, existing-flow migration, production service recovery and cleanup of
partially applied policy after cancellation remain follow-up work.
Never run the fixture example in the host namespace.

The namespace fixture disables IPv4 reverse-path filtering within its isolated
namespace, because unmarked QUIC replies otherwise fail the VPN table lookup.
A production platform must provide a compatible reverse-path/packet-mark policy.
