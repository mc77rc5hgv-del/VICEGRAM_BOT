# Signed manifest v1

Wire envelope: JSON with payload (a UTF-8 string) and signature (64 byte integers).
Sign Ed25519 over the bytes VOLNA-MANIFEST-V1 followed by a zero byte, then the exact
payload UTF-8 bytes. There is no JSON reserialization before verification:
whitespace/key-order changes require a new signature. Private signing keys belong
only to the control-plane publisher; client code receives a pinned public key.

The typed payload includes schema, monotonically increasing version, issued_at,
expires_at (Unix seconds), HTTPS health_url, edges, status, failure domains,
transport endpoints, SNI and leaf certificate pin. No user credentials.
Schema validation rejects duplicate edges/transports, unknown fields and missing
Hysteria pins. Manifest lifetime is locally capped at 7 days; offline grace at
24 hours. Clock reversal fails closed. A 60-second issuance clock tolerance is allowed.

ConfigClient tries up to three HTTPS endpoints with TLS verification, no redirects,
no environment proxies, a 2-second timeout per endpoint, and a 128 KiB envelope cap.
Invalid signatures/expiry/version never replace the cache; the next endpoint is tried.
Payload cap is 64 KiB. Config failures can use only the newest accepted signed manifest,
within its expiry or explicit local grace. An older cached version never returns:
this would risk resurrecting an edge revoked by a later version.

ConfigStore keeps three verified manifests in memory. snapshot/restore exchange
signed bytes; version_floor and last_observed_time are explicit persistence state.
The platform MUST persist the signed snapshot, version floor and clock high-water
mark atomically in protected storage before activating an updated configuration.
This increment does not implement disk/Keystore persistence. Recreating a store
with floor=0 loses rollback protection across restarts; deleting app data resets it.
Restoring an expired signed manifest retains its version floor without making it usable.

The verified wrapper alone can produce Hysteria routes, excluding draining/disabled
edges. Device username/password pairs come from a separate secure credential store.
No automatic hot-switching of an existing session is performed by ConfigClient.
Signing-key rotation and revocation are not implemented; provision the pinned public
key through the platform until a reviewed rotation mechanism is available.

Tests cover tampering, wrong keys, rollback/equivocation, expiry/grace, future issuance,
clock reversal, expired-cache restore, edge filtering, and a real local HTTPS API:
malformed primary -> valid signed secondary -> tampered response -> cached fallback.
