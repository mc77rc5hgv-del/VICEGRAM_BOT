//! Signed control-plane manifests. Sign exact UTF-8 payload bytes plus DOMAIN.
//! Private verified wrapper prevents unverified JSON from becoming route config.
use std::{collections::{HashMap, HashSet, VecDeque}, time::Duration};
use ed25519_dalek::{Signature, VerifyingKey};
use serde::{Deserialize, Serialize};

pub const DOMAIN: &[u8] = b"VOLNA-MANIFEST-V1\0";
pub const MAX_PAYLOAD: usize = 65536;
pub const MAX_ENVELOPE: usize = 131072;
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Envelope { pub payload: String, pub signature: Vec<u8> }
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Manifest {
    pub schema: u32,
    pub version: u64,
    pub issued_at: u64,
    pub expires_at: u64,
    pub health_url: String,
    pub edges: Vec<Edge>,
}
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Edge {
    pub id: String,
    pub failure_domain: String,
    pub status: EdgeStatus,
    pub endpoints: Vec<Endpoint>,
}
#[derive(Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum EdgeStatus { Active, Draining, Disabled }
#[derive(Clone, Copy, Serialize, Deserialize, PartialEq, Eq, Hash)]
#[serde(rename_all = "snake_case")]
pub enum Protocol { Awg, Masque, TcpTls, Hysteria2 }
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Endpoint {
    pub protocol: Protocol,
    pub address: std::net::SocketAddr,
    pub sni: Option<String>,
    pub certificate_pin: Option<String>,
}
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ConfigError {
    Oversized, Signature, Schema, ClockRollback, Future, Expired,
    Rollback, Equivocation, EmptyCache, Endpoints, Fetch,
}
#[derive(Clone)]
pub struct VerifiedManifest { manifest: Manifest, envelope: Envelope }
impl VerifiedManifest {
    pub fn manifest(&self) -> &Manifest { &self.manifest }
    /// Only active Hysteria endpoints become runtime configuration. Credentials
    /// are device-specific and must be provided separately from a secure store.
    #[cfg(unix)]
    pub fn hysteria_routes(&self, credentials: &HashMap<String,(String,String)>)
        -> Vec<crate::hysteria::HysteriaRoute> {
        self.manifest.edges.iter().filter(|e| e.status == EdgeStatus::Active)
            .flat_map(|edge| {
                edge.endpoints.iter().filter(|p| p.protocol == Protocol::Hysteria2)
                    .filter_map(move |endpoint| {
                        let (username,password) = credentials.get(&edge.id)?;
                        Some(crate::hysteria::HysteriaRoute {
                            route_id: edge.id.clone(),server: endpoint.address,
                            username: username.clone(),password: password.clone(),
                            sni: endpoint.sni.clone()?,
                            certificate_pin: endpoint.certificate_pin.clone()?,
                        })
                    })
            }).collect()
    }
}
#[derive(Clone)]
pub struct Verifier { key: VerifyingKey }
impl Verifier {
    pub fn new(public_key: [u8;32]) -> Result<Self,ConfigError> {
        Ok(Self { key: VerifyingKey::from_bytes(&public_key)
            .map_err(|_| ConfigError::Signature)? })
    }
    pub fn verify(&self, envelope: Envelope) -> Result<VerifiedManifest,ConfigError> {
        if envelope.payload.len() > MAX_PAYLOAD { return Err(ConfigError::Oversized); }
        let signature = Signature::from_slice(&envelope.signature)
            .map_err(|_| ConfigError::Signature)?;
        let mut message = Vec::with_capacity(DOMAIN.len()+envelope.payload.len());
        message.extend_from_slice(DOMAIN);
        message.extend_from_slice(envelope.payload.as_bytes());
        self.key.verify_strict(&message,&signature).map_err(|_| ConfigError::Signature)?;
        // Parse only after authentication; serde rejects duplicate/unknown fields.
        let manifest: Manifest = serde_json::from_str(&envelope.payload)
            .map_err(|_| ConfigError::Schema)?;
        validate(&manifest)?;
        Ok(VerifiedManifest { manifest, envelope })
    }
}
fn validate(m: &Manifest) -> Result<(),ConfigError> {
    if m.schema != 1 || m.version == 0 || m.issued_at >= m.expires_at
        || m.expires_at-m.issued_at > 7*24*3600 || m.edges.is_empty() || m.edges.len() > 128 {
        return Err(ConfigError::Schema);
    }
    let url = reqwest::Url::parse(&m.health_url).map_err(|_| ConfigError::Schema)?;
    if url.scheme() != "https" || url.host_str().is_none()
        || !url.username().is_empty() || url.password().is_some() || url.fragment().is_some() {
        return Err(ConfigError::Schema);
    }
    let mut ids = HashSet::new();
    for edge in &m.edges {
        if edge.id.is_empty() || edge.id.len() > 128 || edge.failure_domain.is_empty()
            || edge.failure_domain.len() > 128 || !ids.insert(&edge.id)
            || edge.endpoints.is_empty() || edge.endpoints.len() > 4 {
            return Err(ConfigError::Schema);
        }
        let mut protocols = HashSet::new();
        for endpoint in &edge.endpoints {
            if endpoint.address.port() == 0 || endpoint.address.ip().is_unspecified()
                || !protocols.insert(endpoint.protocol) {
                return Err(ConfigError::Schema);
            }
            if endpoint.protocol == Protocol::Hysteria2 {
                let sni = endpoint.sni.as_deref().ok_or(ConfigError::Schema)?;
                let pin = endpoint.certificate_pin.as_deref().ok_or(ConfigError::Schema)?;
                if sni.is_empty() || sni.len() > 253 || pin.len() != 64
                    || !pin.bytes().all(|b| b.is_ascii_hexdigit()) {
                    return Err(ConfigError::Schema);
                }
            }
        }
    }
    Ok(())
}
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Source { Remote, Cached, OfflineGrace }
pub struct LoadedConfig { pub config: VerifiedManifest, pub source: Source }
pub struct ConfigStore {
    verifier: Verifier,
    floor: u64,
    last_time: u64,
    grace: u64,
    history: VecDeque<VerifiedManifest>,
}
impl ConfigStore {
    /// floor and last_time must come from protected persistent platform storage.
    /// Remote config cannot widen the local grace policy (maximum 24 hours).
    pub fn new(verifier: Verifier, floor: u64, last_time: u64, grace: Duration) -> Self {
        Self { verifier,floor,last_time,grace: grace.as_secs().min(24*3600),
            history: VecDeque::new() }
    }
    pub fn version_floor(&self) -> u64 { self.floor }
    pub fn last_observed_time(&self) -> u64 { self.last_time }
    fn check_time(&mut self, now: u64) -> Result<(),ConfigError> {
        if now < self.last_time { return Err(ConfigError::ClockRollback); }
        self.last_time = now;
        Ok(())
    }
    fn insert(&mut self, verified: VerifiedManifest, now: u64) -> Result<(),ConfigError> {
        let m = &verified.manifest;
        if m.issued_at > now.saturating_add(60) { return Err(ConfigError::Future); }
        if m.version < self.floor { return Err(ConfigError::Rollback); }
        if let Some(existing) = self.history.front() {
            if existing.manifest.version == m.version
                && existing.envelope.payload != verified.envelope.payload {
                return Err(ConfigError::Equivocation);
            }
            if existing.manifest.version == m.version { return Ok(()); }
        }
        self.floor = m.version;
        self.history.push_front(verified);
        self.history.truncate(3);
        Ok(())
    }
    pub fn accept(&mut self, envelope: Envelope, now: u64)
        -> Result<LoadedConfig,ConfigError> {
        self.check_time(now)?;
        let verified = self.verifier.verify(envelope)?;
        if now >= verified.manifest.expires_at { return Err(ConfigError::Expired); }
        self.insert(verified.clone(),now)?;
        Ok(LoadedConfig { config: verified,source: Source::Remote })
    }
    /// Restore previously persisted signed bytes, including expired manifests,
    /// so expiry does not erase the anti-rollback floor.
    pub fn restore(&mut self, envelope: Envelope, now: u64) -> Result<(),ConfigError> {
        self.check_time(now)?;
        let verified = self.verifier.verify(envelope)?;
        self.insert(verified,now)
    }
    pub fn cache(&mut self, now: u64) -> Result<LoadedConfig,ConfigError> {
        self.check_time(now)?;
        let config = self.history.front().ok_or(ConfigError::EmptyCache)?.clone();
        // Never fall back to an older version: it may resurrect a revoked edge.
        if config.manifest.version < self.floor { return Err(ConfigError::Rollback); }
        let source = if now < config.manifest.expires_at { Source::Cached }
            else if now < config.manifest.expires_at.saturating_add(self.grace) {
                Source::OfflineGrace
            } else { return Err(ConfigError::Expired); };
        Ok(LoadedConfig { config,source })
    }
    /// Signed cache and floor/time must be saved atomically by the platform.
    pub fn snapshot(&self) -> Option<Envelope> {
        self.history.front().map(|v| v.envelope.clone())
    }
}
pub struct ConfigClient { endpoints: Vec<reqwest::Url>, client: reqwest::Client }
impl ConfigClient {
    pub fn new(endpoints: &[String]) -> Result<Self,ConfigError> {
        Self::with_ca(endpoints,None)
    }
    /// For private control APIs: trust an explicit CA without disabling TLS checks.
    pub fn with_ca(endpoints: &[String], ca: Option<reqwest::Certificate>)
        -> Result<Self,ConfigError> {
        if endpoints.is_empty() || endpoints.len() > 3 { return Err(ConfigError::Endpoints); }
        let mut urls = Vec::new();
        for endpoint in endpoints {
            let url = reqwest::Url::parse(endpoint).map_err(|_| ConfigError::Endpoints)?;
            if url.scheme() != "https" || url.host_str().is_none()
                || !url.username().is_empty() || url.password().is_some() || url.fragment().is_some() {
                return Err(ConfigError::Endpoints);
            }
            if !urls.contains(&url) { urls.push(url); }
        }
        let mut builder = reqwest::Client::builder().no_proxy()
            .redirect(reqwest::redirect::Policy::none()).timeout(Duration::from_secs(2));
        if let Some(ca) = ca { builder = builder.add_root_certificate(ca); }
        let client = builder.build().map_err(|_| ConfigError::Fetch)?;
        Ok(Self { endpoints: urls,client })
    }
    async fn envelope(&self, url: &reqwest::Url) -> Result<Envelope,ConfigError> {
        let mut response = self.client.get(url.clone()).send().await
            .map_err(|_| ConfigError::Fetch)?;
        if response.status() != reqwest::StatusCode::OK { return Err(ConfigError::Fetch); }
        if response.content_length().is_some_and(|len| len > MAX_ENVELOPE as u64) {
            return Err(ConfigError::Oversized);
        }
        let mut bytes = Vec::new();
        while let Some(chunk) = response.chunk().await.map_err(|_| ConfigError::Fetch)? {
            if bytes.len().saturating_add(chunk.len()) > MAX_ENVELOPE {
                return Err(ConfigError::Oversized);
            }
            bytes.extend_from_slice(&chunk);
        }
        serde_json::from_slice(&bytes).map_err(|_| ConfigError::Schema)
    }
    /// Sequential independent bootstrap addresses, bounded to 3 x 2 seconds.
    /// now is supplied by the platform clock and is refreshed after network IO.
    /// Clock rollback fails closed rather than extending offline grace.
    pub async fn refresh(&self, store: &mut ConfigStore,
        clock: impl Fn() -> u64) -> Result<LoadedConfig,ConfigError> {
        for endpoint in &self.endpoints {
            if let Ok(envelope) = self.envelope(endpoint).await {
                match store.accept(envelope,clock()) {
                    Ok(config) => return Ok(config),
                    Err(ConfigError::ClockRollback) => return Err(ConfigError::ClockRollback),
                    Err(_) => {}
                }
            }
        }
        store.cache(clock())
    }
}
