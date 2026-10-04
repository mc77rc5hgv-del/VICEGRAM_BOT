#![cfg(unix)]
use std::{path::PathBuf, sync::Arc, time::Duration};
use tokio::sync::watch;
use volna_core::{*, runtime::*, hysteria::*};

fn attempt() -> Attempt {
    Attempt { start_after: Duration::ZERO, score: 95.0,
        route: Route { id: "hy".into(), failure_domain: "fixture".into(),
            transport: Transport::Hysteria2, accepting_connections: true,
            metrics: Metrics { success_probability: 1.0,rtt_ms: 1.0,loss: 0.0,
                jitter_ms: 0.0,server_load: 0.0,stability: 1.0,
                historical_success: 1.0,transport_cost: 0.0,battery_cost: 0.0 } } }
}
fn connector(password: &str, pin: String, server: String) -> HysteriaConnector {
    let ca = reqwest::Certificate::from_pem(
        &std::fs::read(std::env::var("VOLNA_TEST_CA").unwrap()).unwrap()).unwrap();
    HysteriaConnector::new(PathBuf::from(std::env::var("VOLNA_HYSTERIA_BIN").unwrap()),
        vec![HysteriaRoute { route_id: "hy".into(), server: server.parse().unwrap(),
            username: "volna".into(), password: password.into(), sni: "localhost".into(),
            certificate_pin: pin }],std::env::var("VOLNA_TEST_HEALTH").unwrap(),
        Some(ca)).unwrap()
}
fn processes() -> Vec<u32> {
    let mut children = Vec::new();
    for task in std::fs::read_dir("/proc/self/task").unwrap() {
        let path = task.unwrap().path().join("children");
        children.extend(std::fs::read_to_string(path).unwrap_or_default()
            .split_whitespace().filter_map(|pid| pid.parse::<u32>().ok()));
    }
    children

}
#[tokio::test]
#[ignore = "requires tests/hysteria_fixture.py and verified Hysteria2 binary"]
async fn real_quic_auth_pin_shutdown_and_cancellation() {
    let endpoint = std::env::var("VOLNA_HYSTERIA_SERVER").unwrap();
    let pin = std::env::var("VOLNA_HYSTERIA_PIN").unwrap();
    let options = RaceOptions { deadline: Duration::from_secs(8),
        attempt_timeout: Duration::from_secs(6), ..RaceOptions::default() };
    let (_tx,rx) = watch::channel(1);
    let c = Arc::new(connector("fixture-password",pin.clone(),endpoint.clone()));
    let winner = connect_race(c.clone(),vec![attempt()],options,rx.clone(),1)
        .await.unwrap();
    let pid = winner.session.process_id().unwrap();
    assert!(PathBuf::from(format!("/proc/{pid}")).exists());
    let body = winner.session.client()
        .get(std::env::var("VOLNA_TEST_HEALTH").unwrap().replace("/health","/payload"))
        .send().await.unwrap().text().await.unwrap();
    assert_eq!(body,"volna-real-quic");
    // A managed child must own a private config without argv credentials.
    let cmdline = std::fs::read(format!("/proc/{pid}/cmdline")).unwrap();
    assert!(!String::from_utf8_lossy(&cmdline).contains("fixture-password"));
    let cfg = cmdline.split(|b| *b == 0).map(|b| String::from_utf8_lossy(b).to_string())
        .find(|arg| arg.ends_with("/client.json")).unwrap();
    use std::os::unix::fs::PermissionsExt;
    assert_eq!(std::fs::metadata(&cfg).unwrap().permissions().mode() & 0o777,0o600);
    winner.session.shutdown().await.unwrap();
    assert!(!PathBuf::from(format!("/proc/{pid}")).exists());
    assert!(!PathBuf::from(&cfg).exists());

    for (password, cert_pin) in [
        ("wrong-password",pin.clone()),
        ("fixture-password","00".repeat(32)),
    ] {
        let bad = Arc::new(connector(password,cert_pin,endpoint.clone()));
        assert!(connect_race(bad,vec![attempt()],options,rx.clone(),1).await.is_err());
    }
    // Drop winner (race loser uses the same RAII) must also stop its child.
    let winner = connect_race(c,vec![attempt()],options,rx,1).await.unwrap();
    let dropped_pid = winner.session.process_id().unwrap();
    drop(winner);
    for _ in 0..100 {
        if !PathBuf::from(format!("/proc/{dropped_pid}")).exists() { break; }
        tokio::time::sleep(Duration::from_millis(20)).await;
    }
    assert!(!PathBuf::from(format!("/proc/{dropped_pid}")).exists());
    let (tx,rx) = watch::channel(1);
    let hung = Arc::new(connector("fixture-password",pin,
        std::env::var("VOLNA_HYSTERIA_DEAD_SERVER").unwrap()));
    let cancel = async {
        tokio::time::sleep(Duration::from_millis(200)).await;
        tx.send(2).unwrap();
    };
    let (result,()) = tokio::join!(
        connect_race(hung,vec![attempt()],options,rx,1),cancel);
    assert!(matches!(result,Err(RaceError::Cancelled)));
    for _ in 0..100 {
        if processes().is_empty() { break; }
        tokio::time::sleep(Duration::from_millis(20)).await;
    }
    assert!(processes().is_empty(),"cancelled/failed clients must be reaped");
    let temp = PathBuf::from(std::env::var("TMPDIR").unwrap());
    assert!(!std::fs::read_dir(temp).unwrap().any(|entry|
        entry.unwrap().file_name().to_string_lossy().starts_with("volna-hy-")));
}

#[tokio::test]
#[ignore = "real two-edge fixture"]
async fn supervisor_prewarm_and_real_edge_failure_switches_quic_path() {
    use volna_core::supervisor::*;
    let primary = std::env::var("VOLNA_HYSTERIA_SERVER").unwrap();
    let backup = std::env::var("VOLNA_HYSTERIA_BACKUP_SERVER").unwrap();
    let pin = std::env::var("VOLNA_HYSTERIA_PIN").unwrap();
    let ca = reqwest::Certificate::from_pem(
        &std::fs::read(std::env::var("VOLNA_TEST_CA").unwrap()).unwrap()).unwrap();
    let routes = vec![("primary",primary),("backup",backup)].into_iter()
        .map(|(id,endpoint)| HysteriaRoute { route_id: id.into(),server: endpoint.parse().unwrap(),
            username: "volna".into(),password: "fixture-password".into(),sni: "localhost".into(),
            certificate_pin: pin.clone() }).collect();
    let c = Arc::new(HysteriaConnector::new(
        PathBuf::from(std::env::var("VOLNA_HYSTERIA_BIN").unwrap()),routes,
        std::env::var("VOLNA_TEST_HEALTH").unwrap(),Some(ca)).unwrap());
    let mut primary_route = attempt().route;
    primary_route.id = "primary".into(); primary_route.failure_domain = "a".into();
    let mut backup_route = primary_route.clone();
    backup_route.id = "backup".into(); backup_route.failure_domain = "b".into();
    backup_route.metrics.rtt_ms = 500.0;
    let (tx,rx) = watch::channel(1);
    let (active_tx,active_rx) = watch::channel(None);
    let (status_tx,mut status_rx) = watch::channel(SupervisorStatus::default());
    let options = SupervisorOptions {
        interval: Duration::from_millis(100),probe_timeout: Duration::from_millis(300),
        degraded_rtt: Duration::ZERO,degraded_samples: 1,
        improvement_margin: Duration::from_secs(60),cooldown: Duration::ZERO,
        race: RaceOptions { deadline: Duration::from_secs(6),
            attempt_timeout: Duration::from_secs(5),good_enough_score: 95.0,
            ..RaceOptions::default() },..SupervisorOptions::default() };
    let task = tokio::spawn(supervise(c,vec![primary_route,backup_route],
        Mode::Auto,options,SupervisorChannels { generation: rx,active: active_tx,status: status_tx },1));
    tokio::time::timeout(Duration::from_secs(12),async {
        loop {
            if status_rx.borrow().backup_ready { break; }
            status_rx.changed().await.unwrap();
        }
    }).await.unwrap();
    assert_eq!(active_rx.borrow().as_ref().unwrap().route_id,"primary");
    std::fs::write(std::env::var("VOLNA_STOP_PRIMARY").unwrap(),b"stop").unwrap();
    tokio::time::timeout(Duration::from_secs(12),async {
        loop {
            if status_rx.borrow().switches > 0 { break; }
            status_rx.changed().await.unwrap();
        }
    }).await.unwrap();
    let selected = active_rx.borrow().as_ref().unwrap().clone();
    assert_eq!(selected.route_id,"backup");
    let body = selected.handle.get(std::env::var("VOLNA_TEST_HEALTH").unwrap()
        .replace("/health","/payload")).send().await.unwrap().text().await.unwrap();
    assert_eq!(body,"volna-real-quic");
    tx.send(2).unwrap();
    assert_eq!(task.await.unwrap(),Err(SupervisorError::Cancelled));
    assert!(active_rx.borrow().is_none());
    for _ in 0..100 {
        if processes().is_empty() { break; }
        tokio::time::sleep(Duration::from_millis(20)).await;
    }
    assert!(processes().is_empty());
}
