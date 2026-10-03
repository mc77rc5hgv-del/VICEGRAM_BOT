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
direct-traffic blocking before activation, blocking after shutdown and restoration
after explicit disconnect. It never changes the host default route. The binary
release and certificate pin are verified.

System-route activation is not yet wired to the HTTP supervisor. Android VpnService,
DNS ownership, existing-flow migration, production service recovery and cleanup of
partially applied policy after cancellation remain follow-up work.
Never run the fixture example in the host namespace.
