//! HTTP data-path adapter for independently supervised Hysteria2 SOCKS proxies.
//! This is not an IP/TUN transport and does not authenticate Hysteria itself.
use std::{collections::HashMap, net::SocketAddr, time::Duration};
use crate::{Attempt, Transport, runtime::{Connector, ConnectError, ConnectFuture}};
use reqwest::{Client, Proxy, Url, redirect::Policy};

pub struct ProxyRoute {
    pub route_id: String,
    pub socks_address: SocketAddr,
}
pub struct SocksConnector {
    clients: HashMap<String, Client>,
    health_url: Url,
}
pub struct SocksSession { client: Client }
impl SocksSession {
    /// Every request uses the selected proxy; socks5h resolves names at the exit.
    /// Caller owns response size limits, application deadlines and content policy.
    pub fn client(&self) -> &Client { &self.client }
}
#[derive(Debug, PartialEq, Eq)]
pub enum ConfigError { InvalidHealthUrl, InvalidProxy, DuplicateRoute, Client }

impl SocksConnector {
    /// Production supplies None for extra_ca. A private health service may supply
    /// its trusted CA; certificate verification is always enabled.
    pub fn new(routes: Vec<ProxyRoute>, health_url: &str,
        extra_ca: Option<reqwest::Certificate>) -> Result<Self, ConfigError> {
        Self::with_auth(routes, health_url, extra_ca, None)
    }
    pub(crate) fn with_auth(routes: Vec<ProxyRoute>, health_url: &str,
        extra_ca: Option<reqwest::Certificate>, auth: Option<(&str, &str)>)
        -> Result<Self, ConfigError> {
        let health_url = Url::parse(health_url).map_err(|_| ConfigError::InvalidHealthUrl)?;
        if health_url.scheme() != "https" || health_url.host_str().is_none()
            || !health_url.username().is_empty() || health_url.password().is_some()
            || health_url.fragment().is_some() {
            return Err(ConfigError::InvalidHealthUrl);
        }
        let mut clients = HashMap::new();
        for route in routes {
            if route.route_id.is_empty() || !route.socks_address.ip().is_loopback()
                || route.socks_address.port() == 0 {
                return Err(ConfigError::InvalidProxy);
            }
            if clients.contains_key(&route.route_id) { return Err(ConfigError::DuplicateRoute); }
            let mut proxy = Proxy::all(format!("socks5h://{}", route.socks_address))
                .map_err(|_| ConfigError::InvalidProxy)?;
            if let Some((user, password)) = auth {
                proxy = proxy.basic_auth(user,password);
            }
            let mut builder = Client::builder().no_proxy().proxy(proxy)
                .redirect(Policy::none()).timeout(Duration::from_secs(5))
                .connect_timeout(Duration::from_secs(2))
                .pool_max_idle_per_host(0);
            if let Some(ca) = extra_ca.clone() { builder = builder.add_root_certificate(ca); }
            let client = builder.build().map_err(|_| ConfigError::Client)?;
            clients.insert(route.route_id,client);
        }
        Ok(Self { clients, health_url })
    }
}
impl Connector for SocksConnector {
    type Session = SocksSession;
    fn supports(&self, transport: Transport) -> bool { transport == Transport::Hysteria2 }
    fn connect<'a>(&'a self, attempt: &'a Attempt) -> ConnectFuture<'a, Self::Session> {
        Box::pin(async move {
            if attempt.route.transport != Transport::Hysteria2 {
                return Err(ConnectError::Unavailable);
            }
            let client = self.clients.get(&attempt.route.id)
                .ok_or(ConnectError::Unavailable)?.clone();
            let response = client.get(self.health_url.clone()).send().await
                .map_err(|_| ConnectError::HealthCheck)?;
            if response.status() != reqwest::StatusCode::NO_CONTENT {
                return Err(ConnectError::HealthCheck);
            }
            Ok(SocksSession { client })
        })
    }
}
