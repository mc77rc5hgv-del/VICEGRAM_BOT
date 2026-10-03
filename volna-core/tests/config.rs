use std::time::Duration;
use ed25519_dalek::{Signer,SigningKey};
use volna_core::config::*;

fn key() -> SigningKey { SigningKey::from_bytes(&[7u8;32]) }
fn verifier() -> Verifier { Verifier::new(key().verifying_key().to_bytes()).unwrap() }
fn manifest(version: u64) -> Manifest {
    Manifest { schema: 1,version,issued_at: 100,expires_at: 200,
        health_url: "https://health.example/health".into(),
        edges: vec![Edge { id: "fi-1".into(), failure_domain: "provider-a".into(),
            status: EdgeStatus::Active,endpoints: vec![Endpoint {
                protocol: Protocol::Hysteria2,address: "192.0.2.1:443".parse().unwrap(),
                sni: Some("edge.example".into()),certificate_pin: Some("ab".repeat(32)),
            }] }] }
}
fn sign(m: &Manifest) -> Envelope {
    let payload = serde_json::to_string(m).unwrap();
    let mut message = DOMAIN.to_vec();
    message.extend_from_slice(payload.as_bytes());
    Envelope { payload,signature: key().sign(&message).to_bytes().to_vec() }
}
fn store() -> ConfigStore {
    ConfigStore::new(verifier(),0,0,Duration::from_secs(50))
}
#[test]
fn tampering_wrong_key_and_wrong_signature_size_are_rejected() {
    let mut e = sign(&manifest(1));
    e.payload = e.payload.replace("192.0.2.1","192.0.2.2");
    assert!(matches!(verifier().verify(e),Err(ConfigError::Signature)));
    let other = Verifier::new(SigningKey::from_bytes(&[8u8;32])
        .verifying_key().to_bytes()).unwrap();
    assert!(matches!(other.verify(sign(&manifest(1))),Err(ConfigError::Signature)));
    let mut e = sign(&manifest(1)); e.signature.truncate(63);
    assert!(matches!(verifier().verify(e),Err(ConfigError::Signature)));
}
#[test]
fn rejects_rollback_and_equivocation_without_poisoning_cache() {
    let mut s = store();
    s.accept(sign(&manifest(2)),120).unwrap();
    assert!(matches!(s.accept(sign(&manifest(1)),121),Err(ConfigError::Rollback)));
    let mut changed = manifest(2);
    changed.edges[0].status = EdgeStatus::Disabled;
    assert!(matches!(s.accept(sign(&changed),122),Err(ConfigError::Equivocation)));
    assert_eq!(s.cache(123).unwrap().config.manifest().version,2);
}
#[test]
fn grace_is_local_bounded_and_never_resurrects_older_manifest() {
    let mut s = store();
    s.accept(sign(&manifest(1)),120).unwrap();
    let mut newer = manifest(2); newer.expires_at = 180;
    s.accept(sign(&newer),130).unwrap();
    assert_eq!(s.cache(180).unwrap().source,Source::OfflineGrace);
    assert_eq!(s.cache(180).unwrap().config.manifest().version,2);
    assert!(matches!(s.cache(230),Err(ConfigError::Expired)));
}
#[test]
fn clock_reversal_future_and_remote_expiry_fail_closed() {
    let mut s = store();
    s.accept(sign(&manifest(1)),120).unwrap();
    assert!(matches!(s.cache(119),Err(ConfigError::ClockRollback)));
    let mut future = manifest(2); future.issued_at = 300; future.expires_at = 400;
    assert!(matches!(s.accept(sign(&future),121),Err(ConfigError::Future)));
    assert!(matches!(s.accept(sign(&manifest(2)),200),Err(ConfigError::Expired)));
}
#[test]
fn signed_cache_restore_keeps_floor_after_expiry() {
    let mut s = store(); s.accept(sign(&manifest(5)),120).unwrap();
    let mut restored = ConfigStore::new(verifier(),s.version_floor(),
        s.last_observed_time(),Duration::ZERO);
    restored.restore(s.snapshot().unwrap(),300).unwrap();
    assert_eq!(restored.version_floor(),5);
    assert!(matches!(restored.cache(300),Err(ConfigError::Expired)));
    let mut old = manifest(4); old.issued_at = 250; old.expires_at = 400;
    assert!(matches!(restored.accept(sign(&old),300),Err(ConfigError::Rollback)));
}
#[test]
fn signed_bad_schema_duplicate_edges_and_missing_pins_are_rejected() {
    let mut m = manifest(1); m.edges.push(m.edges[0].clone());
    assert!(matches!(verifier().verify(sign(&m)),Err(ConfigError::Schema)));
    let mut m = manifest(1); m.edges[0].endpoints[0].certificate_pin = None;
    assert!(matches!(verifier().verify(sign(&m)),Err(ConfigError::Schema)));
    let mut m = manifest(1); m.schema = 2;
    assert!(matches!(verifier().verify(sign(&m)),Err(ConfigError::Schema)));
}
#[cfg(unix)]
#[test]
fn only_verified_active_edges_with_separate_credentials_reach_hysteria() {
    let mut m = manifest(1);
    let mut second = m.edges[0].clone(); second.id = "draining".into();
    second.status = EdgeStatus::Draining; m.edges.push(second);
    let verified = verifier().verify(sign(&m)).unwrap();
    let creds = std::collections::HashMap::from([
        ("fi-1".into(),("user".into(),"secret".into())),
        ("draining".into(),("user".into(),"secret".into())),
    ]);
    let routes = verified.hysteria_routes(&creds);
    assert_eq!(routes.len(),1);
    assert_eq!(routes[0].route_id,"fi-1");
    assert_eq!(routes[0].certificate_pin,"ab".repeat(32));
}
