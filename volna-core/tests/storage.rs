#![cfg(unix)]
use std::{path::PathBuf,time::Duration,os::unix::fs::PermissionsExt};
use ed25519_dalek::{Signer,SigningKey};
use volna_core::{config::*,storage::*};
fn private_dir() -> tempfile::TempDir {
    let dir = tempfile::tempdir().unwrap();
    std::fs::set_permissions(dir.path(),std::fs::Permissions::from_mode(0o700)).unwrap();
    dir
}
fn verifier() -> Verifier {
    Verifier::new(SigningKey::from_bytes(&[11u8;32]).verifying_key().to_bytes()).unwrap()
}
fn envelope(version: u64) -> Envelope {
    let m = Manifest { schema: 1,version,issued_at: 100,expires_at: 200,
        health_url: "https://health.example/health".into(),edges: vec![Edge {
            id: "fi".into(),failure_domain: "provider-a".into(),status: EdgeStatus::Active,
            endpoints: vec![Endpoint { protocol: Protocol::Hysteria2,
                address: "192.0.2.1:443".parse().unwrap(),sni: Some("edge.example".into()),
                certificate_pin: Some("ab".repeat(32)) }] }] };
    let payload = serde_json::to_string(&m).unwrap();
    let mut bytes = DOMAIN.to_vec(); bytes.extend_from_slice(payload.as_bytes());
    Envelope { payload,signature: SigningKey::from_bytes(&[11u8;32])
        .sign(&bytes).to_bytes().to_vec() }
}
fn create(path: PathBuf) -> PersistentConfigStore {
    PersistentConfigStore::create(path,verifier(),0,100,Duration::from_secs(50)).unwrap()
}
fn open(path: PathBuf,now: u64) -> Result<PersistentConfigStore,StorageError> {
    PersistentConfigStore::open(path,verifier(),0,100,Duration::from_secs(50),now)
}
#[test]
fn restart_preserves_signed_routes_floor_clock_and_private_permissions() {
    let dir = private_dir(); let path = dir.path().join("manifest.json");
    let mut store = create(path.clone());
    store.accept(envelope(5),120).unwrap();
    assert_eq!(std::fs::metadata(&path).unwrap().permissions().mode() & 0o777,0o600);
    drop(store);
    let mut restored = open(path.clone(),130).unwrap();
    assert_eq!(restored.cache(130).unwrap().config.manifest().version,5);
    assert!(matches!(restored.accept(envelope(4),131),
        Err(StorageError::Config(ConfigError::Rollback))));
    drop(restored);
    assert!(matches!(open(path,129),Err(StorageError::Config(ConfigError::ClockRollback))));
}
#[test]
fn expiry_progress_survives_restart_and_no_older_routes_return() {
    let dir = private_dir(); let path = dir.path().join("manifest.json");
    let mut s = create(path.clone()); s.accept(envelope(3),120).unwrap();
    assert!(matches!(s.cache(250),Err(StorageError::Config(ConfigError::Expired))));
    drop(s);
    assert!(matches!(open(path.clone(),249),Err(StorageError::Config(ConfigError::ClockRollback))));
    let mut s = open(path,251).unwrap();
    assert_eq!(s.version_floor(),3);
    assert!(matches!(s.cache(251),Err(StorageError::Config(ConfigError::Expired))));
}
#[test]
fn one_writer_and_explicit_initialization() {
    let dir = private_dir(); let path = dir.path().join("manifest.json");
    assert!(matches!(open(path.clone(),100),Err(StorageError::Missing)));
    let first = create(path.clone());
    assert!(matches!(open(path.clone(),100),Err(StorageError::Locked)));
    drop(first);
    assert!(matches!(PersistentConfigStore::create(path,verifier(),0,100,Duration::ZERO),
        Err(StorageError::Exists)));
}
#[test]
fn corrupt_missing_or_replaced_cache_never_resets_accepted_version() {
    let dir = private_dir(); let path = dir.path().join("manifest.json");
    let mut s = create(path.clone()); s.accept(envelope(6),120).unwrap(); drop(s);
    let original = std::fs::read(&path).unwrap();
    let mut json: serde_json::Value = serde_json::from_slice(&original).unwrap();
    json["floor"] = serde_json::json!(5);
    std::fs::write(&path,serde_json::to_vec(&json).unwrap()).unwrap();
    assert!(matches!(open(path.clone(),130),Err(StorageError::Corrupt)));
    std::fs::write(&path,b"truncated").unwrap();
    assert!(matches!(open(path.clone(),130),Err(StorageError::Corrupt)));
    std::fs::remove_file(&path).unwrap();
    assert!(matches!(open(path,130),Err(StorageError::Missing)));
}
#[test]
fn failed_commit_does_not_activate_candidate_or_allow_stale_fallback() {
    let dir = private_dir(); let path = dir.path().join("manifest.json");
    let mut s = create(path.clone()); s.accept(envelope(1),120).unwrap();
    let before = std::fs::read(&path).unwrap();
    std::fs::set_permissions(dir.path(),std::fs::Permissions::from_mode(0o755)).unwrap();
    assert!(matches!(s.accept(envelope(2),130),Err(StorageError::Permissions)));
    assert_eq!(s.version_floor(),1);
    assert_eq!(std::fs::read(&path).unwrap(),before);
    assert!(matches!(s.cache(131),Err(StorageError::Poisoned)));
    std::fs::set_permissions(dir.path(),std::fs::Permissions::from_mode(0o700)).unwrap();
    drop(s);
    assert_eq!(open(path,132).unwrap().version_floor(),1);
}
#[test]
fn rejects_symlinks_hardlinks_and_world_readable_cache() {
    let dir = private_dir(); let path = dir.path().join("manifest.json");
    let s = create(path.clone()); drop(s);
    std::fs::set_permissions(&path,std::fs::Permissions::from_mode(0o644)).unwrap();
    assert!(matches!(open(path.clone(),100),Err(StorageError::Permissions)));
    std::fs::set_permissions(&path,std::fs::Permissions::from_mode(0o600)).unwrap();
    let other = dir.path().join("other"); std::fs::hard_link(&path,&other).unwrap();
    assert!(matches!(open(path.clone(),100),Err(StorageError::Permissions)));
    std::fs::remove_file(&path).unwrap();
    std::os::unix::fs::symlink(&other,&path).unwrap();
    assert!(open(path,100).is_err());
}
