//! Unix process adapter for Hysteria2 v2.12.3. SOCKS health path and optional Linux native TUN.
use std::{collections::HashMap, io::Write, net::{Ipv4Addr, TcpListener},
    os::unix::fs::{OpenOptionsExt,PermissionsExt}, path::PathBuf, process::Stdio, time::Duration};
use rand::{rngs::OsRng, RngCore};
use serde_json::json;
use tempfile::TempDir;
use tokio::{process::{Child, Command}, time::sleep};
use crate::{Attempt, Transport, runtime::{Connector, ConnectError, ConnectFuture},
    socks::{ProxyRoute, SocksConnector, SocksSession}};

/// No Debug/Serialize implementation: credentials must never enter diagnostics.
pub struct HysteriaRoute {
    pub route_id: String,
    pub server: std::net::SocketAddr,
    pub username: String,
    pub password: String,
    pub sni: String,
    /// SHA256 of the leaf certificate DER, 64 hex digits (colons accepted).
    pub certificate_pin: String,
}
pub struct HysteriaConnector {
    #[cfg(target_os="linux")]
    tun_profiles: HashMap<String,crate::tun::TunProfile>,
    executable: PathBuf,
    routes: HashMap<String,HysteriaRoute>,
    health_url: String,
    health_ca: Option<reqwest::Certificate>,
}
#[derive(Debug, PartialEq, Eq)]
pub enum HysteriaConfigError { Executable, Route, Pin, Health }
pub struct HysteriaSession {
    #[cfg(target_os="linux")]
    tun_interface: Option<String>,
    proxy: SocksSession,
    child: Child,
    _directory: TempDir,
}
impl HysteriaSession {
    #[cfg(target_os="linux")]
    pub fn tun_interface(&self) -> Option<&str> { self.tun_interface.as_deref() }
    pub fn client(&self) -> &reqwest::Client { self.proxy.client() }
    pub fn process_id(&self) -> Option<u32> { self.child.id() }
    /// Deterministically kills and reaps the owned process before deleting config.
    /// Drop/cancellation also requests termination through Tokio kill_on_drop.
    pub async fn shutdown(mut self) -> std::io::Result<()> {
        self.child.kill().await
    }
}
impl HysteriaConnector {
    pub fn new(executable: PathBuf, routes: Vec<HysteriaRoute>,
        health_url: String, health_ca: Option<reqwest::Certificate>)
        -> Result<Self,HysteriaConfigError> {
        if !executable.is_absolute() || !executable.is_file() {
            return Err(HysteriaConfigError::Executable);
        }
        SocksConnector::new(vec![],&health_url,health_ca.clone())
            .map_err(|_| HysteriaConfigError::Health)?;
        let mut indexed = HashMap::new();
        for mut route in routes {
            if route.route_id.is_empty() || route.server.port() == 0
                || route.server.ip().is_unspecified()
                || route.username.is_empty() || route.username.contains(':')
                || route.password.is_empty() || route.sni.is_empty()
                || route.username.len() > 256 || route.password.len() > 4096
                || route.sni.len() > 253 || route.route_id.len() > 256
                || indexed.contains_key(&route.route_id) {
                return Err(HysteriaConfigError::Route);
            }
            route.certificate_pin = route.certificate_pin.replace(':',"").to_lowercase();
            if route.certificate_pin.len() != 64
                || !route.certificate_pin.bytes().all(|b| b.is_ascii_hexdigit()) {
                return Err(HysteriaConfigError::Pin);
            }
            indexed.insert(route.route_id.clone(),route);
        }
        Ok(Self { executable, routes: indexed, health_url, health_ca,
            #[cfg(target_os="linux")]
            tun_profiles: HashMap::new(),
        })
    }
}
fn secret() -> String {
    let mut bytes = [0u8;32];
    OsRng.fill_bytes(&mut bytes);
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}
impl Connector for HysteriaConnector {
    type Session = HysteriaSession;
    fn supports(&self, transport: Transport) -> bool { transport == Transport::Hysteria2 }
    fn connect<'a>(&'a self, attempt: &'a Attempt) -> ConnectFuture<'a,Self::Session> {
        Box::pin(async move {
            if attempt.route.transport != Transport::Hysteria2 {
                return Err(ConnectError::Unavailable);
            }
            let route = self.routes.get(&attempt.route.id).ok_or(ConnectError::Unavailable)?;
            // Hold the port until immediately before spawn. Random SOCKS credentials
            // prevent accepting an unrelated listener if the port is stolen.
            let reservation = TcpListener::bind((Ipv4Addr::LOCALHOST,0))
                .map_err(|_| ConnectError::Unavailable)?;
            let address = reservation.local_addr().map_err(|_| ConnectError::Unavailable)?;
            let proxy_user = secret();
            let proxy_password = secret();
            let directory = tempfile::Builder::new().prefix("volna-hy-").tempdir()
                .map_err(|_| ConnectError::Unavailable)?;
            std::fs::set_permissions(directory.path(),std::fs::Permissions::from_mode(0o700))
                .map_err(|_| ConnectError::Unavailable)?;
            let config_path = directory.path().join("client.json");
            #[allow(unused_mut)]
            let mut config = json!({
                "server": route.server.to_string(),
                "auth": format!("{}:{}",route.username,route.password),
                "tls": {
                    "sni": route.sni,
                    // Pin-only mode supports the existing self-signed deployment.
                    // Hysteria still verifies pinSHA256 in VerifyPeerCertificate.
                    "insecure": true,
                    "pinSHA256": route.certificate_pin
                },
                "lazy": false,
                "socks5": {
                    "listen": address.to_string(), "username": proxy_user,
                    "password": proxy_password, "disableUDP": true
                }
            });
            #[cfg(target_os="linux")]
            let profile = self.tun_profiles.get(&route.route_id);
            #[cfg(target_os="linux")]
            if let Some(profile) = profile {
                if crate::tun::interface_exists(profile.interface()) {
                    return Err(ConnectError::Unavailable);
                }
                config["tun"] = profile.config();
                config["quic"] = json!({"sockopts": {"fwmark": crate::tun::TRANSPORT_MARK}});
            }
            let mut file = std::fs::OpenOptions::new().write(true).create_new(true)
                .mode(0o600).open(&config_path).map_err(|_| ConnectError::Unavailable)?;
            serde_json::to_writer(&mut file,&config).map_err(|_| ConnectError::Unavailable)?;
            file.flush().map_err(|_| ConnectError::Unavailable)?;
            drop(file);
            let proxy = SocksConnector::with_auth(vec![ProxyRoute {
                route_id: route.route_id.clone(), socks_address: address
            }], &self.health_url, self.health_ca.clone(),
                Some((&proxy_user,&proxy_password))).map_err(|_| ConnectError::Unavailable)?;
            drop(reservation);
            let mut child = Command::new(&self.executable)
                .arg("client").arg("--config").arg(&config_path)
                .arg("--disable-update-check").arg("--log-level").arg("error")
                .env_clear().stdin(Stdio::null()).stdout(Stdio::null()).stderr(Stdio::null())
                .kill_on_drop(true).spawn().map_err(|_| ConnectError::Unavailable)?;
            loop {
                if child.try_wait().map_err(|_| ConnectError::Unavailable)?.is_some() {
                    return Err(ConnectError::Unavailable);
                }
                // Outer connect_race deadline cancels this future and owned child.
                if let Ok(session) = proxy.connect(attempt).await {
                    if child.try_wait().map_err(|_| ConnectError::Unavailable)?.is_some() {
                        return Err(ConnectError::Unavailable);
                    }
                    #[cfg(target_os="linux")]
                    if let Some(profile) = profile {
                        if !crate::tun::interface_exists(profile.interface()) {
                            sleep(Duration::from_millis(20)).await;
                            continue;
                        }
                    }
                    return Ok(HysteriaSession { proxy: session, child, _directory: directory,
                        #[cfg(target_os="linux")]
                        tun_interface: profile.map(|p| p.interface().to_string()),
                    });
                }
                sleep(Duration::from_millis(50)).await;
            }
        })
    }
}

impl crate::supervisor::MonitoredConnector for HysteriaConnector {
    type Handle = reqwest::Client;
    fn handle(&self,session: &HysteriaSession) -> Self::Handle { session.client().clone() }
    fn health<'a>(&'a self,session: &'a mut HysteriaSession)
        -> crate::supervisor::HealthFuture<'a> {
        Box::pin(async move {
            if session.child.try_wait().map_err(|_| ())?.is_some() { return Err(()); }
            let started = tokio::time::Instant::now();
            let response = session.client().get(&self.health_url).send().await.map_err(|_| ())?;
            if response.status() != reqwest::StatusCode::NO_CONTENT
                || session.child.try_wait().map_err(|_| ())?.is_some() { return Err(()); }
            Ok(crate::supervisor::HealthSample { rtt: started.elapsed() })
        })
    }
}

#[cfg(target_os="linux")]
impl HysteriaConnector {
    /// Enables candidate TUN devices without automatic default route changes.
    /// LinuxPolicyRouter owns activation; CAP_NET_ADMIN/root is required.
    pub fn with_tun(mut self,profiles: HashMap<String,crate::tun::TunProfile>)
        -> Result<Self,HysteriaConfigError> {
        let mut names = std::collections::HashSet::new();
        let mut slots = std::collections::HashSet::new();
        for (route,profile) in &profiles {
            if !self.routes.contains_key(route) || !names.insert(profile.interface())
                || !slots.insert(profile.slot()) { return Err(HysteriaConfigError::Route); }
        }
        self.tun_profiles = profiles;
        Ok(self)
    }
}
