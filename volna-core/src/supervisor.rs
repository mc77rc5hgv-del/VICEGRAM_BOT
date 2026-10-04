//! Continuous health/prewarm/failover for a single owned application data path.
//! Publication swaps handles for NEW requests. This does not migrate TUN/TCP flows.
use std::{future::Future,pin::Pin,sync::Arc,time::Duration};
use tokio::{sync::watch,time::{Instant,timeout}};
use crate::{Route,Mode,State,race_plan,backup_plan,
    runtime::{Connector,Winner,RaceError,RaceOptions,connect_race}};

pub struct HealthSample { pub rtt: Duration }
pub type HealthFuture<'a> =
    Pin<Box<dyn Future<Output=Result<HealthSample,()>>+Send+'a>>;
pub trait MonitoredConnector: Connector {
    type Handle: Clone+Send+Sync;
    fn handle(&self,session: &Self::Session) -> Self::Handle;
    fn health<'a>(&'a self,session: &'a mut Self::Session) -> HealthFuture<'a>;
}
#[derive(Clone)]
pub struct ActivePath<H: Clone> { pub route_id: String,pub handle: H }
#[derive(Clone,Debug)]
pub struct SupervisorStatus {
    pub state: State,pub active_route: Option<String>,pub backup_ready: bool,pub switches: u64,
}
impl Default for SupervisorStatus {
    fn default() -> Self {
        Self { state: State::Idle,active_route: None,backup_ready: false,switches: 0 }
    }
}
#[derive(Clone,Copy)]
pub struct SupervisorOptions {
    pub race: RaceOptions,pub interval: Duration,pub probe_timeout: Duration,
    pub degraded_rtt: Duration,pub improvement_margin: Duration,
    pub failed_samples: u32,pub degraded_samples: u32,
    pub cooldown: Duration,pub reserve_ttl: Duration,pub retry_delay: Duration,
}
impl Default for SupervisorOptions {
    fn default() -> Self {
        Self { race: RaceOptions::default(),interval: Duration::from_secs(2),
            probe_timeout: Duration::from_secs(2),degraded_rtt: Duration::from_millis(300),
            improvement_margin: Duration::from_millis(50),failed_samples: 2,
            degraded_samples: 3,cooldown: Duration::from_secs(10),
            reserve_ttl: Duration::from_secs(30),retry_delay: Duration::from_secs(2) }
    }
}
pub struct SupervisorChannels<H: Clone> {
    pub generation: watch::Receiver<u64>,
    pub active: watch::Sender<Option<ActivePath<H>>>,
    pub status: watch::Sender<SupervisorStatus>,
}
#[derive(Debug,PartialEq,Eq)]
pub enum SupervisorError { Options,Cancelled,Connect(RaceError),Unavailable,Activation }
struct Publication<H: Clone> {
    active: watch::Sender<Option<ActivePath<H>>>,
    status: watch::Sender<SupervisorStatus>,final_state: State,
}
impl<H: Clone> Drop for Publication<H> {
    fn drop(&mut self) {
        self.active.send_replace(None);
        self.status.send_replace(SupervisorStatus { state: self.final_state,
            ..SupervisorStatus::default() });
    }
}
fn publish<C: MonitoredConnector>(c: &C,p: &Publication<C::Handle>,
    active: &Winner<C::Session>,state: State,ready: bool,switches: u64) {
    p.status.send_replace(SupervisorStatus { state,
        active_route: Some(active.attempt.route.id.clone()),backup_ready: ready,switches });
    if state == State::Connected {
        p.active.send_replace(Some(ActivePath { route_id: active.attempt.route.id.clone(),
            handle: c.handle(&active.session) }));
    }
}
async fn probe<C: MonitoredConnector>(c: &C,session: &mut C::Session,
    limit: Duration,epoch: &mut watch::Receiver<u64>,expected: u64)
    -> Result<Result<HealthSample,()>,SupervisorError> {
    if *epoch.borrow() != expected || epoch.has_changed().is_err() {
        return Err(SupervisorError::Cancelled);
    }
    tokio::select! {
        biased;
        _ = epoch.changed() => Err(SupervisorError::Cancelled),
        result = timeout(limit,c.health(session)) => Ok(result.unwrap_or(Err(()))),
    }
}
/// Platform activation runs before publication and before dropping the old session.
/// Activation must retain fail-closed guards on errors or future cancellation.
#[derive(Debug,PartialEq,Eq)]
pub enum ActivationError { Retryable,Fatal }
pub type ActivationFuture<'a> = Pin<Box<dyn Future<Output=Result<(),ActivationError>>+Send+'a>>;
pub trait PathActivator<S>: Send {
    fn activate<'a>(&'a mut self,session: &'a S) -> ActivationFuture<'a>;
}
pub struct ApplicationOnly;
impl<S> PathActivator<S> for ApplicationOnly {
    fn activate<'a>(&'a mut self,_session: &'a S) -> ActivationFuture<'a> {
        Box::pin(async { Ok(()) })
    }
}
type Pending<S> = Pin<Box<dyn Future<Output=Result<Winner<S>,RaceError>>+Send>>;
pub async fn supervise<C: MonitoredConnector+'static>(connector: Arc<C>,routes: Vec<Route>,
    mode: Mode,options: SupervisorOptions,channels: SupervisorChannels<C::Handle>,epoch: u64)
    -> Result<(),SupervisorError> where C::Session: 'static {
    supervise_with_activation(connector,routes,mode,options,channels,epoch,&mut ApplicationOnly).await
}
/// Epoch cancellation waits for an in-flight activation to finish. Aborting the
/// task may interrupt platform work; guards must survive that case.
pub async fn supervise_with_activation<C: MonitoredConnector+'static,A: PathActivator<C::Session>>(
    connector: Arc<C>,routes: Vec<Route>,mode: Mode,options: SupervisorOptions,
    channels: SupervisorChannels<C::Handle>,epoch: u64,activator: &mut A)
    -> Result<(),SupervisorError> where C::Session: 'static {
    let mut publication = Publication { active: channels.active,status: channels.status,
        final_state: State::Idle };
    let result = run(connector,routes,mode,options,channels.generation,epoch,&publication,activator).await;
    if !matches!(result,Err(SupervisorError::Cancelled)) { publication.final_state = State::Failed; }
    result
}
#[allow(clippy::too_many_arguments)]
async fn run<C: MonitoredConnector+'static,A: PathActivator<C::Session>>(c: Arc<C>,routes: Vec<Route>,mode: Mode,
    o: SupervisorOptions,mut epoch: watch::Receiver<u64>,expected: u64,
    p: &Publication<C::Handle>,activator: &mut A) -> Result<(),SupervisorError> where C::Session: 'static {
    if o.interval.is_zero() || o.probe_timeout.is_zero() || o.reserve_ttl.is_zero()
        || o.retry_delay.is_zero() || o.failed_samples == 0 || o.degraded_samples == 0 {
        return Err(SupervisorError::Options);
    }
    p.status.send_replace(SupervisorStatus { state: State::Racing,..SupervisorStatus::default() });
    let mut active = connect_race(c.clone(),race_plan(&routes,mode,
        Duration::from_millis(100),o.race.max_attempts),o.race,epoch.clone(),expected)
        .await.map_err(|e| if e == RaceError::Cancelled { SupervisorError::Cancelled }
            else { SupervisorError::Connect(e) })?;
    if *epoch.borrow() != expected || epoch.has_changed().is_err() {
        return Err(SupervisorError::Cancelled);
    }
    activator.activate(&active.session).await.map_err(|_| SupervisorError::Activation)?;
    if *epoch.borrow() != expected || epoch.has_changed().is_err() {
        return Err(SupervisorError::Cancelled);
    }
    publish(c.as_ref(),p,&active,State::Connected,false,0);
    let mut pending: Option<Pending<C::Session>> = None;
    let mut reserve: Option<(Winner<C::Session>,Instant)> = None;
    let mut failures = 0u32;
    let mut degraded = 0u32;
    let mut switches = 0u64;
    let mut next_retry = Instant::now();
    let mut cooldown = Instant::now();
    let mut backoff = o.retry_delay;
    let mut ticker = tokio::time::interval(o.interval);
    ticker.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
    loop {
        tokio::select! {
            biased;
            _ = epoch.changed() => return Err(SupervisorError::Cancelled),
            result = async { pending.as_mut().expect("guarded").await }, if pending.is_some() => {
                pending = None;
                if *epoch.borrow() != expected { return Err(SupervisorError::Cancelled); }
                match result {
                    Ok(winner) => {
                        reserve = Some((winner,Instant::now()));
                        backoff = o.retry_delay;
                        publish(c.as_ref(),p,&active,State::Degraded,true,switches);
                    }
                    Err(RaceError::Cancelled) => return Err(SupervisorError::Cancelled),
                    Err(_) => {
                        next_retry = Instant::now()+backoff;
                        backoff = backoff.saturating_mul(2).min(Duration::from_secs(30));
                        if failures >= o.failed_samples { return Err(SupervisorError::Unavailable); }
                        publish(c.as_ref(),p,&active,State::Degraded,false,switches);
                    }
                }
            }
            _ = ticker.tick() => {
                let sample = probe(c.as_ref(),&mut active.session,o.probe_timeout,
                    &mut epoch,expected).await?;
                match &sample {
                    Ok(health) => {
                        failures = 0;
                        if health.rtt >= o.degraded_rtt { degraded = degraded.saturating_add(1); }
                        else { degraded = 0; }
                    }
                    Err(()) => { failures = failures.saturating_add(1); }
                }
                if let Some((backup,created)) = reserve.as_mut() {
                    if created.elapsed() >= o.reserve_ttl {
                        reserve = None;
                    } else {
                        let backup_health = probe(c.as_ref(),&mut backup.session,o.probe_timeout,
                            &mut epoch,expected).await?;
                        let better = match (&sample,&backup_health) {
                            (Ok(active),Ok(backup)) =>
                                backup.rtt.saturating_add(o.improvement_margin) < active.rtt,
                            (Err(()),Ok(_)) => true,
                            _ => false,
                        };
                        if backup_health.is_err() {
                            reserve = None;
                            next_retry = Instant::now()+backoff;
                        } else if better && Instant::now() >= next_retry && (failures >= o.failed_samples
                            || (degraded >= o.degraded_samples && Instant::now() >= cooldown)) {
                            // Fresh backup validation precedes publication; old process
                            // is dropped only after swapping the handle for new requests.
                            publish(c.as_ref(),p,&active,State::Migrating,true,switches);
                            if *epoch.borrow() != expected { return Err(SupervisorError::Cancelled); }
                            let activation = activator.activate(&reserve.as_ref().expect("validated").0.session).await;
                            if activation == Err(ActivationError::Fatal) {
                                return Err(SupervisorError::Activation);
                            }
                            if activation == Err(ActivationError::Retryable) {
                                if *epoch.borrow() != expected || epoch.has_changed().is_err() {
                                    return Err(SupervisorError::Cancelled);
                                }
                                next_retry = Instant::now()+backoff;
                                backoff = backoff.saturating_mul(2).min(Duration::from_secs(30));
                                publish(c.as_ref(),p,&active,State::Degraded,true,switches);
                                continue;
                            }
                            if *epoch.borrow() != expected || epoch.has_changed().is_err() {
                                return Err(SupervisorError::Cancelled);
                            }
                            let old = std::mem::replace(&mut active,
                                reserve.take().expect("validated").0);
                            failures = 0; degraded = 0;
                            switches = switches.saturating_add(1);
                            cooldown = Instant::now()+o.cooldown;
                            publish(c.as_ref(),p,&active,State::Connected,false,switches);
                            drop(old);
                            continue;
                        }
                    }
                }
                let impaired = failures > 0 || degraded >= o.degraded_samples;
                if impaired {
                    if reserve.is_none() && pending.is_none() && Instant::now() >= next_retry
                        && (failures > 0 || Instant::now() >= cooldown) {
                        let plan = backup_plan(&routes,&active.attempt.route,mode);
                        if plan.is_empty() && failures >= o.failed_samples {
                            return Err(SupervisorError::Unavailable);
                        }
                        if !plan.is_empty() {
                            pending = Some(Box::pin(connect_race(c.clone(),plan,o.race,
                                epoch.clone(),expected)));
                            publish(c.as_ref(),p,&active,State::PreparingBackup,false,switches);
                        }
                    }
                    if pending.is_none() {
                        publish(c.as_ref(),p,&active,State::Degraded,reserve.is_some(),switches);
                    }
                } else {
                    // Recovery cancels unnecessary connection work but keeps a ready
                    // standby until its bounded TTL for a subsequent hard failure.
                    pending = None;
                    publish(c.as_ref(),p,&active,State::Connected,reserve.is_some(),switches);
                }
            }
        }
    }
}
