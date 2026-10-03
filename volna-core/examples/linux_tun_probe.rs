//! Privileged fixture only. Never run in the host namespace.
#[cfg(target_os="linux")]
#[tokio::main(flavor="current_thread")]
async fn main() {
    use std::{collections::HashMap,path::PathBuf,time::Duration};
    use volna_core::{*,hysteria::*,tun::*};
    let env = |name| std::env::var(name).unwrap();
    let ca = reqwest::Certificate::from_pem(&std::fs::read(env("VOLNA_TEST_CA")).unwrap()).unwrap();
    let profile = TunProfile::new("volna0".into(),1).unwrap();
    let mut router = LinuxPolicyRouter::install(PathBuf::from(env("VOLNA_IP")),20000,20000).await.unwrap();
    use std::sync::Arc;
    use tokio::sync::watch;
    use volna_core::supervisor::*;
    let backup_profile = TunProfile::new("volna1".into(),2).unwrap();
    let routes = [("hy",env("VOLNA_HYSTERIA_SERVER")),("backup",env("VOLNA_HYSTERIA_BACKUP_SERVER"))]
        .into_iter().map(|(id,endpoint)| HysteriaRoute { route_id: id.into(),
            server: endpoint.parse().unwrap(),username: "volna".into(),
            password: "fixture-password".into(),sni: "localhost".into(),
            certificate_pin: env("VOLNA_HYSTERIA_PIN") }).collect();
    let c = Arc::new(HysteriaConnector::new(PathBuf::from(env("VOLNA_HYSTERIA_BIN")),
        routes,env("VOLNA_TEST_HEALTH"),Some(ca.clone())).unwrap().with_tun(
        HashMap::from([("hy".into(),profile.clone()),("backup".into(),backup_profile.clone())])).unwrap());
    let primary = Route { id: "hy".into(),failure_domain: "a".into(),transport: Transport::Hysteria2,
        accepting_connections: true,metrics: Metrics { success_probability: 1.0,rtt_ms: 1.0,
            loss: 0.0,jitter_ms: 0.0,server_load: 0.0,stability: 1.0,
            historical_success: 1.0,transport_cost: 0.0,battery_cost: 0.0 } };
    let mut backup = primary.clone();
    backup.id = "backup".into(); backup.failure_domain = "b".into(); backup.metrics.rtt_ms = 500.0;
    let (tx,rx) = watch::channel(1);
    let (active_tx,active_rx) = watch::channel(None);
    let (status_tx,mut status_rx) = watch::channel(SupervisorStatus::default());
    let options = SupervisorOptions { interval: Duration::from_millis(100),
        probe_timeout: Duration::from_millis(400),degraded_rtt: Duration::ZERO,
        degraded_samples: 1,improvement_margin: Duration::from_secs(60),
        cooldown: Duration::ZERO,race: volna_core::runtime::RaceOptions {
            deadline: Duration::from_secs(8),attempt_timeout: Duration::from_secs(6),
            ..volna_core::runtime::RaceOptions::default() },..SupervisorOptions::default() };
    let client = reqwest::Client::builder().no_proxy().add_root_certificate(ca)
        .timeout(Duration::from_secs(2)).pool_max_idle_per_host(0).build().unwrap();
    let url = env("VOLNA_TEST_HEALTH").replace("/health","/payload");
    assert!(client.get(&url).send().await.is_err());
    let worker = tokio::spawn(async move {
        let result = {
            let mut activation = HysteriaTunActivator { router: &mut router };
            supervise_with_activation(c,vec![primary,backup],Mode::Auto,options,
                SupervisorChannels { generation: rx,active: active_tx,status: status_tx },
                1,&mut activation).await
        };
        (result,router)
    });
    tokio::time::timeout(Duration::from_secs(15),async {
        loop { if status_rx.borrow().backup_ready { break; } status_rx.changed().await.unwrap(); }
    }).await.unwrap();
    assert_eq!(active_rx.borrow().as_ref().unwrap().route_id,"hy");
    assert_eq!(client.get(&url).send().await.unwrap().text().await.unwrap(),"volna-real-quic");
    async fn echo(endpoint: String) {
        // Blocking recv runs off the supervisor's single-thread runtime.
        tokio::task::spawn_blocking(move || {
            let udp = std::net::UdpSocket::bind("0.0.0.0:0").unwrap();
            udp.set_read_timeout(Some(Duration::from_secs(3))).unwrap();
            udp.send_to(b"volna-udp",endpoint).unwrap();
            let mut buf = [0u8;32];
            let (n,_) = udp.recv_from(&mut buf).unwrap();
            assert_eq!(&buf[..n],b"volna-udp");
        }).await.unwrap();
    }
    echo(env("VOLNA_UDP")).await;
    std::fs::write(env("VOLNA_STOP_PRIMARY"),b"stop").unwrap();
    tokio::time::timeout(Duration::from_secs(15),async {
        loop { if status_rx.borrow().switches > 0 { break; } status_rx.changed().await.unwrap(); }
    }).await.unwrap();
    assert!(PathBuf::from(env("VOLNA_ROUTE_FAILURE")).exists());
    assert_eq!(active_rx.borrow().as_ref().unwrap().route_id,"backup");
    assert_eq!(client.get(&url).send().await.unwrap().text().await.unwrap(),"volna-real-quic");
    echo(env("VOLNA_UDP")).await;
    // Confirm the kernel table actually selected the reserve, independently of status.
    let output = tokio::process::Command::new(env("VOLNA_IP"))
        .args(["-4","-j","route","show","table","20000"]).output().await.unwrap();
    let routes: Vec<serde_json::Value> = serde_json::from_slice(&output.stdout).unwrap();
    assert!(routes.iter().any(|r| r["dev"] == "volna1" && r["metric"] == 10));
    tx.send(2).unwrap();
    let (result,mut router) = worker.await.unwrap();
    assert_eq!(result,Err(SupervisorError::Cancelled));
    assert!(active_rx.borrow().is_none());
    for _ in 0..100 {
        if !interface_exists(profile.interface()) && !interface_exists(backup_profile.interface()) { break; }
        tokio::time::sleep(Duration::from_millis(20)).await;
    }
    assert!(!interface_exists(profile.interface()));
    assert!(!interface_exists(backup_profile.interface()));
    assert!(client.get(&url).send().await.is_err());
    router.disconnect().await.unwrap();
    assert_eq!(client.get(&url).send().await.unwrap().text().await.unwrap(),"volna-real-quic");
    println!("TUN failover with dual-stack rollback and automatic retry: HTTPS/UDP, kernel reserve route, cancellation guard and disconnect passed");
}
#[cfg(not(target_os="linux"))]
fn main() {}
