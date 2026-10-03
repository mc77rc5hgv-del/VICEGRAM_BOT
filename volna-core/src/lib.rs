//! Connection policy only: this crate does not open sockets or install routes.
//! Platform adapters must authenticate tunnels and validate end-to-end health.
use std::time::Duration;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Transport { Awg, Masque, TcpTls, Hysteria2 }

/// Implementations must keep standby tunnels separate from the active TUN route.
/// A successful connect must mean authenticated, usable IP connectivity.
pub trait TransportAdapter {
    type Session;
    type Error;
    fn transport(&self) -> Transport;
    fn connect(&mut self, route: &Route, timeout: Duration)
        -> Result<Self::Session, Self::Error>;
    fn close(&mut self, session: Self::Session);
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Mode { Auto, Fast }

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum State {
    Idle, Profiling, Discovering, Racing, Connected, Degraded,
    PreparingBackup, Migrating, NoConnectivity, Failed,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Event {
    Start, ProfileReady, CandidatesReady, TunnelReady, QualityDropped,
    PrepareBackup, BackupReady, MigrationSucceeded, MigrationFailed,
    QualityRecovered, AttemptsExhausted, BackupFailed, NetworkLost,
    NetworkRestored, Stop,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct InvalidTransition { pub state: State, pub event: Event }

#[derive(Debug)]
pub struct StateMachine { state: State }
impl Default for StateMachine {
    fn default() -> Self { Self { state: State::Idle } }
}
impl StateMachine {
    pub fn state(&self) -> State { self.state }
    pub fn apply(&mut self, event: Event) -> Result<State, InvalidTransition> {
        use Event::*;
        use State::*;
        let next = match (self.state, event) {
            (_, Stop) => Idle,
            (Idle | Failed, Start) => Profiling,
            (Profiling, ProfileReady) => Discovering,
            (Discovering, CandidatesReady) => Racing,
            (Racing, TunnelReady) => Connected,
            (Connected, QualityDropped) => Degraded,
            (Degraded, PrepareBackup) => PreparingBackup,
            (PreparingBackup, BackupReady) => Migrating,
            (Migrating, MigrationSucceeded) => Connected,
            (Migrating, MigrationFailed) => Degraded,
            (Degraded | PreparingBackup, QualityRecovered) => Connected,
            (PreparingBackup, BackupFailed) => Degraded,
            (Racing | Profiling | Discovering, AttemptsExhausted) => Failed,
            (Profiling | Discovering | Racing | Connected | Degraded |
                PreparingBackup | Migrating, NetworkLost) => NoConnectivity,
            (NoConnectivity, NetworkRestored) => Profiling,
            _ => return Err(InvalidTransition { state: self.state, event }),
        };
        self.state = next;
        Ok(next)
    }
}

#[derive(Debug, Clone)]
pub struct Metrics {
    pub success_probability: f64,
    pub rtt_ms: f64,
    pub loss: f64,
    pub jitter_ms: f64,
    pub server_load: f64,
    pub stability: f64,
    pub historical_success: f64,
    pub transport_cost: f64,
    pub battery_cost: f64,
}
impl Metrics {
    /// Reject unknown/invalid values instead of promoting them to healthy routes.
    pub fn score(&self, mode: Mode) -> Option<f64> {
        let units = [self.success_probability, self.loss, self.server_load,
            self.stability, self.historical_success, self.transport_cost,
            self.battery_cost];
        if units.iter().any(|v| !v.is_finite() || !(0.0..=1.0).contains(v))
            || !self.rtt_ms.is_finite() || self.rtt_ms < 0.0
            || !self.jitter_ms.is_finite() || self.jitter_ms < 0.0 {
            return None;
        }
        let latency = 1.0 / (1.0 + self.rtt_ms / 100.0);
        let jitter = 1.0 / (1.0 + self.jitter_ms / 30.0);
        let values = [self.success_probability, latency, 1.0-self.loss,
            jitter, 1.0-self.server_load, self.stability,
            self.historical_success, 1.0-self.transport_cost,
            1.0-self.battery_cost];
        let weights = match mode {
            Mode::Auto => [0.25,0.10,0.15,0.05,0.05,0.15,0.15,0.05,0.05],
            Mode::Fast => [0.15,0.30,0.15,0.10,0.05,0.10,0.05,0.05,0.05],
        };
        Some(100.0 * values.iter().zip(weights).map(|(v,w)| v*w).sum::<f64>())
    }
}

#[derive(Debug, Clone)]
pub struct Route {
    pub id: String,
    /// Independent provider/site failure domain, not just a country.
    pub failure_domain: String,
    pub transport: Transport,
    pub accepting_connections: bool,
    pub metrics: Metrics,
}

#[derive(Debug, Clone)]
pub struct Attempt { pub route: Route, pub start_after: Duration, pub score: f64 }

/// Produces a bounded staggered schedule. The caller runs attempts concurrently,
/// enforces timeouts, and cancels/closes all losing sessions.
/// No network reachability claims are inferred from a single UDP probe.
pub fn race_plan(routes: &[Route], mode: Mode, stagger: Duration, limit: usize)
    -> Vec<Attempt> {
    let mut ranked: Vec<_> = routes.iter()
        .filter(|r| r.accepting_connections)
        .filter_map(|r| r.metrics.score(mode).map(|s| (r,s))).collect();
    ranked.sort_by(|a,b| b.1.total_cmp(&a.1).then_with(|| a.0.id.cmp(&b.0.id)));
    let mut result: Vec<Attempt> = Vec::new();
    for (route,score) in ranked {
        if result.len() >= limit { break; }
        if result.iter().any(|a| a.route.id == route.id) { continue; }
        result.push(Attempt { route: route.clone(),
            start_after: stagger.saturating_mul(result.len().min(u32::MAX as usize) as u32),
            score });
    }
    result
}

/// Select only authenticated, end-to-end healthy sessions supplied by the caller.
/// Prefer a good-enough route; below threshold, wait until the race deadline.
pub fn choose_ready(ready: &[Attempt], threshold: f64, deadline_reached: bool)
    -> Option<&Attempt> {
    if !threshold.is_finite() || !(0.0..=100.0).contains(&threshold) { return None; }
    ready.iter().filter(|a| a.score.is_finite() && (0.0..=100.0).contains(&a.score))
        .filter(|a| deadline_reached || a.score >= threshold)
        .max_by(|a,b| a.score.total_cmp(&b.score))
}

pub fn backup_plan(routes: &[Route], active: &Route, mode: Mode) -> Vec<Attempt> {
    let eligible: Vec<_> = routes.iter().filter(|r| r.id != active.id
        && r.failure_domain != active.failure_domain).cloned().collect();
    race_plan(&eligible, mode, Duration::from_millis(100), 3)
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum HealthAction { Keep, PrepareBackup }

/// EWMA and consecutive bad samples avoid switching on one noisy observation.
/// Missing samples/timeouts must be handled by the runtime's liveness deadline.
#[derive(Default)]
pub struct HealthMonitor { loss: Option<f64>, bad_samples: u8 }
impl HealthMonitor {
    pub fn observe_loss(&mut self, loss: f64) -> Option<HealthAction> {
        if !loss.is_finite() || !(0.0..=1.0).contains(&loss) { return None; }
        let smoothed = self.loss.map_or(loss, |old| 0.3*loss + 0.7*old);
        self.loss = Some(smoothed);
        if smoothed >= 0.08 {
            self.bad_samples = self.bad_samples.saturating_add(1);
        } else if smoothed <= 0.03 {
            self.bad_samples = 0;
        }
        Some(if self.bad_samples >= 3 { HealthAction::PrepareBackup }
            else { HealthAction::Keep })
    }
}


pub mod runtime;

pub mod socks;

#[cfg(unix)]
pub mod hysteria;

pub mod config;

#[cfg(unix)]
pub mod storage;
