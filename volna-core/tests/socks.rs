use std::{net::{SocketAddr, Ipv4Addr}, sync::Arc, time::Duration};
use tokio::sync::watch;
use volna_core::{*, runtime::*, socks::*};

fn attempt() -> Attempt {
    Attempt { start_after: Duration::ZERO, score: 95.0,
        route: Route { id: "fixture".into(), failure_domain: "fixture".into(),
            transport: Transport::Hysteria2, accepting_connections: true,
            metrics: Metrics { success_probability: 1.0,rtt_ms: 1.0,loss: 0.0,
                jitter_ms: 0.0,server_load: 0.0,stability: 1.0,
                historical_success: 1.0,transport_cost: 0.0,battery_cost: 0.0 } } }
}
#[test]
fn rejects_untrusted_config_shapes() {
    assert!(matches!(SocksConnector::new(vec![],"http://example.com",None),
        Err(ConfigError::InvalidHealthUrl)));
    let remote = ProxyRoute { route_id: "a".into(),
        socks_address: SocketAddr::from((Ipv4Addr::new(192,0,2,1),1080)) };
    assert!(matches!(SocksConnector::new(vec![remote],"https://example.com",None),
        Err(ConfigError::InvalidProxy)));
}
#[tokio::test]
#[ignore = "run through tests/socks_fixture.py: local TLS and SOCKS servers required"]
async fn verified_https_data_path_and_no_direct_fallback() {
    let proxy: SocketAddr = std::env::var("VOLNA_TEST_PROXY").unwrap().parse().unwrap();
    let health = std::env::var("VOLNA_TEST_HEALTH").unwrap();
    let ca = reqwest::Certificate::from_pem(
        &std::fs::read(std::env::var("VOLNA_TEST_CA").unwrap()).unwrap()).unwrap();
    let make = |address, certificate| SocksConnector::new(vec![
        ProxyRoute { route_id: "fixture".into(),socks_address: address }],
        &health,certificate).unwrap();
    let (_tx, rx) = watch::channel(1);
    let winner = connect_race(Arc::new(make(proxy,Some(ca))),
        vec![attempt()],RaceOptions::default(),rx.clone(),1).await.unwrap();
    let body = winner.session.client().get(health.replace("/health","/payload"))
        .send().await.unwrap().text().await.unwrap();
    assert_eq!(body,"volna-through-socks");
    // Same reachable origin, untrusted certificate: must never become ready.
    assert!(connect_race(Arc::new(make(proxy,None)),vec![attempt()],
        RaceOptions::default(),rx.clone(),1).await.is_err());
    let dead: SocketAddr = std::env::var("VOLNA_TEST_DEAD_PROXY").unwrap().parse().unwrap();
    // Reachable HTTPS origin cannot mask an unavailable proxy with direct traffic.
    assert!(connect_race(Arc::new(make(dead,None)),vec![attempt()],
        RaceOptions::default(),rx,1).await.is_err());
}
