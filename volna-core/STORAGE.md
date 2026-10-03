# Durable Unix manifest cache

PersistentConfigStore wraps ConfigStore behind a single-writer advisory lock.
Use create only on explicit first installation; open never creates a missing cache,
repairs corrupted state or resets rollback history. Missing/corrupt files require
platform recovery with an independently protected minimum version and time.

The application supplies an absolute path in its own private directory. Directory
and files must belong to the effective UID, without group/world permissions.
Symlinks at the cache/lock path or immediate parent and hard-linked files are rejected.
Trusted ownership of ancestor directories remains a platform responsibility.
The lock file must not be deleted/replaced while an instance is alive.

Manifest signature, schema and version are checked on load. Signed envelope,
version floor and clock high-water are stored as one JSON record. On update:
validate a cloned candidate -> private temp file -> flush -> file fsync ->
atomic rename -> directory fsync -> publish the candidate in memory.
A failed write poisons the instance: reopen before serving config again, including
when rename succeeds but final fsync fails. Expired-cache access also persists time
so process restart cannot extend offline grace.

ConfigClient.refresh_persistent uses this path; storage failures abort instead of
falling back to an older in-memory config. Disk operations are synchronous and must
run on a dedicated worker/runtime, not an Android or desktop UI thread. One writer
is held for the lifetime of the store. Credentials are not saved in this cache.

This protects normal process restarts and interrupted atomic updates. It cannot
detect replay/deletion of an entire previous valid file by the same UID or a
privileged attacker. Supply external minimum_version/minimum_time anchors from
protected platform storage for that threat. Android Keystore, Windows storage and
hardware counters are not implemented. Disk encryption and key rotation are separate.

Tests cover reopen, expiry/clock persistence, version rejection, writer lock, corrupt
or missing cache, unsafe file permissions/links, and failed writes without activation.
Power-loss guarantees depend on filesystem semantics; tests do not simulate hardware
power failure.
