//! Privileged fixture only. Never run in the host namespace.
#[cfg(target_os="linux")]
#[tokio::main(flavor="current_thread")]
async fn main() {
    use std::{collections::HashMap,path::PathBuf,time::Duration};
    use volna_core::{*,hysteria::*,runtime::Connector,tun::*};
    let env = |name| std::env::var(name).unwrap();
    let ca = reqwest::Certificate::from_pem(&std::fs::read(env("VOLNA_TEST_CA")).unwrap()).unwrap();
    let profile = TunProfile::new("volna0".into(),1).unwrap();
    let mut router = LinuxPolicyRouter::install(PathBuf::from(env("VOLNA_IP")),20000,20000).await.unwrap();
    let c = HysteriaConnector::new(PathBuf::from(env("VOLNA_HYSTERIA_BIN")),
        vec![HysteriaRoute { route_id: "hy".into(),server: env("VOLNA_HYSTERIA_SERVER").parse().unwrap(),
            username: "volna".into(),password: "fixture-password".into(),sni: "localhost".into(),
            certificate_pin: env("VOLNA_HYSTERIA_PIN") }],env("VOLNA_TEST_HEALTH"),Some(ca.clone()))
        .unwrap().with_tun(HashMap::from([("hy".into(),profile.clone())])).unwrap();
    let a = Attempt { start_after: Duration::ZERO,score: 95.0,
        route: Route { id: "hy".into(),failure_domain: "fixture".into(),transport: Transport::Hysteria2,
            accepting_connections: true,metrics: Metrics { success_probability: 1.0,rtt_ms: 1.0,
                loss: 0.0,jitter_ms: 0.0,server_load: 0.0,stability: 1.0,
                historical_success: 1.0,transport_cost: 0.0,battery_cost: 0.0 } } };
    let session = tokio::time::timeout(Duration::from_secs(10),c.connect(&a)).await.unwrap().unwrap();
    let client = reqwest::Client::builder().no_proxy().add_root_certificate(ca)
        .timeout(Duration::from_secs(2)).pool_max_idle_per_host(0).build().unwrap();
    let url = env("VOLNA_TEST_HEALTH").replace("/health","/payload");
    assert!(client.get(&url).send().await.is_err());
    router.activate(&profile).await.unwrap();
    assert_eq!(client.get(&url).send().await.unwrap().text().await.unwrap(),"volna-real-quic");
    let udp = std::net::UdpSocket::bind("0.0.0.0:0").unwrap();
    udp.set_read_timeout(Some(Duration::from_secs(3))).unwrap();
    udp.send_to(b"volna-udp",env("VOLNA_UDP")).unwrap();
    let mut buf = [0u8;32];
    let (n,_) = udp.recv_from(&mut buf).unwrap();
    assert_eq!(&buf[..n],b"volna-udp");
    session.shutdown().await.unwrap();
    assert!(!interface_exists(profile.interface()));
    assert!(client.get(&url).send().await.is_err());
    router.disconnect().await.unwrap();
    assert_eq!(client.get(&url).send().await.unwrap().text().await.unwrap(),"volna-real-quic");
    println!("TUN TCP/UDP, guard and explicit disconnect passed");
}
#[cfg(not(target_os="linux"))]
fn main() {}
