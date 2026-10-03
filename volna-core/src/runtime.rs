//! Async connection races. No detached tasks: dropping the race drops all work.
use crate::{Attempt, Transport};
use futures_util::{stream::FuturesUnordered, StreamExt};
use std::{future::Future, pin::Pin, sync::Arc, time::Duration};
use tokio::{sync::watch, time::{sleep_until, timeout, Instant}};

pub type ConnectFuture<'a, S> =
    Pin<Box<dyn Future<Output = Result<S, ConnectError>> + Send + 'a>>;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ConnectError { Unavailable, Authentication, HealthCheck }

/// Sessions MUST close sockets/tunnels on Drop, including losers and cancellation.
/// connect futures MUST be cancellation-safe: dropping them releases partial
/// resources and must never leave a detached task or installed system route.
/// Ok means authenticated tunnel plus verified end-to-end connectivity.
/// Blocking work must not execute directly on the async runtime.
pub trait Connector: Send + Sync {
    type Session: Send;
    fn supports(&self, transport: Transport) -> bool;
    fn connect<'a>(&'a self, attempt: &'a Attempt) -> ConnectFuture<'a, Self::Session>;
}

#[derive(Debug, Clone, Copy)]
pub struct RaceOptions {
    pub deadline: Duration,
    pub attempt_timeout: Duration,
    pub good_enough_score: f64,
    pub max_attempts: usize,
}
impl Default for RaceOptions {
    fn default() -> Self {
        Self { deadline: Duration::from_secs(4), attempt_timeout: Duration::from_secs(2),
            good_enough_score: 85.0, max_attempts: 4 }
    }
}
#[derive(Debug, PartialEq, Eq)]
pub enum RaceError { InvalidOptions, Cancelled, NoCandidates, Exhausted, Deadline }
pub struct Winner<S> { pub attempt: Attempt, pub session: S }

/// A generation watch value invalidates a race after Stop or a network change.
/// The owner increments it before starting another race. Closing the sender also
/// cancels. Activation of the returned session belongs to the platform runtime.
pub async fn connect_race<C: Connector>(
    connector: Arc<C>, plan: Vec<Attempt>, options: RaceOptions,
    mut generation: watch::Receiver<u64>, expected_generation: u64,
) -> Result<Winner<C::Session>, RaceError> {
    if options.deadline.is_zero() || options.attempt_timeout.is_zero()
        || options.max_attempts == 0 || options.max_attempts > 32
        || !options.good_enough_score.is_finite()
        || !(0.0..=100.0).contains(&options.good_enough_score) {
        return Err(RaceError::InvalidOptions);
    }
    if *generation.borrow() != expected_generation || generation.has_changed().is_err() {
        return Err(RaceError::Cancelled);
    }
    let started = Instant::now();
    let deadline = started.checked_add(options.deadline).ok_or(RaceError::InvalidOptions)?;
    let mut pending = FuturesUnordered::new();
    let mut ids = std::collections::HashSet::new();
    for attempt in plan {
        if pending.len() >= options.max_attempts { break; }
        if !attempt.route.accepting_connections || !connector.supports(attempt.route.transport)
            || !attempt.score.is_finite() || !(0.0..=100.0).contains(&attempt.score)
            || attempt.start_after >= options.deadline || !ids.insert(attempt.route.id.clone()) {
            continue;
        }
        let connector = Arc::clone(&connector);
        pending.push(async move {
            sleep_until(started + attempt.start_after).await;
            let result = timeout(options.attempt_timeout, connector.connect(&attempt)).await;
            (attempt, result)
        });
    }
    if pending.is_empty() { return Err(RaceError::NoCandidates); }
    let mut best: Option<Winner<C::Session>> = None;
    loop {
        tokio::select! {
            biased;
            changed = generation.changed() => {
                if changed.is_err() || *generation.borrow() != expected_generation {
                    return Err(RaceError::Cancelled);
                }
            }
            _ = sleep_until(deadline) => {
                return best.ok_or(RaceError::Deadline);
            }
            completed = pending.next() => {
                // Recheck before returning any session to prevent stale activation.
                if *generation.borrow() != expected_generation || generation.has_changed().is_err() {
                    return Err(RaceError::Cancelled);
                }
                match completed {
                    Some((attempt, Ok(Ok(session)))) => {
                        let candidate = Winner { attempt, session };
                        if candidate.attempt.score >= options.good_enough_score {
                            return Ok(candidate);
                        }
                        if best.as_ref().map_or(true, |old| candidate.attempt.score > old.attempt.score) {
                            best = Some(candidate);
                        }
                    }
                    Some(_) => {}
                    None => return best.ok_or(RaceError::Exhausted),
                }
            }
        }
    }
}
