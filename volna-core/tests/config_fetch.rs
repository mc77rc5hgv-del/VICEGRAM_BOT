use std::time::Duration;
use ed25519_dalek::{Signer,SigningKey};
use volna_core::config::*;
#[tokio::test]
#[ignore = "requires local TLS origin from socks_fixture.py"]
async fn secondary_api_signature_check_and_cached_fallback() {
    let origin = std::env::var("VOLNA_TEST_HEALTH").unwrap().replace("/health","");
    let key = SigningKey::from_bytes(&[9u8;32]);
    let m = Manifest { schema: 1,version: 3,issued_at: 100,expires_at: 200,
        health_url: format!("{origin}/health"),edges: vec![Edge {
            id: "a".into(),failure_domain: "a".into(),status: EdgeStatus::Active,
            endpoints: vec![Endpoint { protocol: Protocol::Hysteria2,
                address: "192.0.2.1:443".parse().unwrap(),sni: Some("edge.example".into()),
                certificate_pin: Some("ab".repeat(32)) }] }] };
    let payload = serde_json::to_string(&m).unwrap();
    let mut message = DOMAIN.to_vec(); message.extend_from_slice(payload.as_bytes());
    let envelope = Envelope { payload,signature: key.sign(&message).to_bytes().to_vec() };
    let path = std::env::var("VOLNA_TEST_MANIFEST").unwrap();
    std::fs::write(&path,serde_json::to_vec(&envelope).unwrap()).unwrap();
    let ca = reqwest::Certificate::from_pem(
        &std::fs::read(std::env::var("VOLNA_TEST_CA").unwrap()).unwrap()).unwrap();
    let client = ConfigClient::with_ca(&[format!("{origin}/invalid"),
        format!("{origin}/manifest")],Some(ca)).unwrap();
    let mut store = ConfigStore::new(Verifier::new(key.verifying_key().to_bytes()).unwrap(),
        0,0,Duration::from_secs(30));
    let fresh = client.refresh(&mut store,||120).await.unwrap();
    assert_eq!(fresh.source,Source::Remote);
    assert_eq!(fresh.config.manifest().version,3);
    let mut tampered = envelope;
    tampered.payload = tampered.payload.replace("192.0.2.1","192.0.2.2");
    std::fs::write(path,serde_json::to_vec(&tampered).unwrap()).unwrap();
    assert_eq!(client.refresh(&mut store,||121).await.unwrap().source,Source::Cached);
    assert_eq!(client.refresh(&mut store,||200).await.unwrap().source,Source::OfflineGrace);
    assert!(matches!(client.refresh(&mut store,||230).await,Err(ConfigError::Expired)));
}
