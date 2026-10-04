use std::{sync::{Arc, atomic::{AtomicUsize, Ordering}}, time::Duration};
use tokio::sync::watch;
use volna_core::{*, runtime::*};

struct Session(Arc<AtomicUsize>);
impl Drop for Session {
    fn drop(&mut self) { self.0.fetch_add(1, Ordering::SeqCst); }
}
struct Fake { closed: Arc<AtomicUsize>, pending: Arc<AtomicUsize> }
struct Pending(Arc<AtomicUsize>);
impl Drop for Pending {
    fn drop(&mut self) { self.0.fetch_sub(1, Ordering::SeqCst); }
}
impl Connector for Fake {
    type Session = Session;
    fn supports(&self, _: Transport) -> bool { true }
    fn connect<'a>(&'a self, a: &'a Attempt) -> ConnectFuture<'a, Session> {
        Box::pin(async move {
            self.pending.fetch_add(1, Ordering::SeqCst);
            let _guard = Pending(self.pending.clone());
            let delay = match a.route.id.as_str() { "hung" => 60_000, "fast" => 10, _ => 50 };
            tokio::time::sleep(Duration::from_millis(delay)).await;
            if a.route.id == "fail" { return Err(ConnectError::Authentication); }
            Ok(Session(self.closed.clone()))
        })
    }
}
fn attempt(id: &str, score: f64, stagger: u64) -> Attempt {
    Attempt { start_after: Duration::from_millis(stagger), score,
        route: Route { id: id.into(), failure_domain: id.into(), transport: Transport::Awg,
            accepting_connections: true, metrics: Metrics {
                success_probability: 1.0, rtt_ms: 10.0, loss: 0.0, jitter_ms: 0.0,
                server_load: 0.0, stability: 1.0, historical_success: 1.0,
                transport_cost: 0.0, battery_cost: 0.0 } } }
}
fn fake() -> Arc<Fake> {
    Arc::new(Fake { closed: Arc::new(AtomicUsize::new(0)),
        pending: Arc::new(AtomicUsize::new(0)) })
}
#[tokio::test(start_paused = true)]
async fn winner_cancels_hung_attempt_and_closes_ready_loser() {
    let c = fake();
    let (_tx, rx) = watch::channel(1);
    let winner = connect_race(c.clone(),vec![attempt("fast",70.0,0),
        attempt("hung",99.0,0),attempt("winner",90.0,0)],
        RaceOptions::default(),rx,1).await.unwrap();
    assert_eq!(winner.attempt.route.id,"winner");
    assert_eq!(c.pending.load(Ordering::SeqCst),0);
    assert_eq!(c.closed.load(Ordering::SeqCst),1);
    drop(winner);
    assert_eq!(c.closed.load(Ordering::SeqCst),2);
}
#[tokio::test(start_paused = true)]
async fn deadline_returns_best_below_threshold() {
    let c = fake();
    let (_tx, rx) = watch::channel(1);
    let options = RaceOptions { deadline: Duration::from_millis(100),
        ..RaceOptions::default() };
    let winner = connect_race(c.clone(),vec![attempt("fast",70.0,0),
        attempt("hung",99.0,0)],options,rx,1).await.unwrap();
    assert_eq!(winner.attempt.route.id,"fast");
    assert_eq!(c.pending.load(Ordering::SeqCst),0);
}
#[tokio::test(start_paused = true)]
async fn generation_change_drops_ready_and_partial_sessions() {
    let c = fake();
    let (tx, rx) = watch::channel(1);
    let race = connect_race(c.clone(),vec![attempt("fast",70.0,0),
        attempt("hung",99.0,0)],RaceOptions::default(),rx,1);
    let change = async {
        tokio::time::sleep(Duration::from_millis(20)).await;
        tx.send(2).unwrap();
    };
    let (result,()) = tokio::join!(race,change);
    assert!(matches!(result,Err(RaceError::Cancelled)));
    assert_eq!(c.pending.load(Ordering::SeqCst),0);
    assert_eq!(c.closed.load(Ordering::SeqCst),1);
}
#[tokio::test(start_paused = true)]
async fn authentication_failure_and_timeout_exhaust_race() {
    let c = fake();
    let (_tx, rx) = watch::channel(1);
    let options = RaceOptions { attempt_timeout: Duration::from_millis(100),
        ..RaceOptions::default() };
    let result = connect_race(c.clone(),vec![attempt("fail",90.0,0),
        attempt("hung",95.0,0)],options,rx,1).await;
    assert!(matches!(result,Err(RaceError::Exhausted)));
    assert_eq!(c.pending.load(Ordering::SeqCst),0);
}
#[tokio::test(start_paused = true)]
async fn cancellation_wins_over_ready_results() {
    let c = fake();
    let (tx, rx) = watch::channel(1);
    tx.send(2).unwrap();
    let result = connect_race(c.clone(),vec![attempt("fast",95.0,0)],
        RaceOptions::default(),rx,1).await;
    assert!(matches!(result,Err(RaceError::Cancelled)));
    assert_eq!(c.pending.load(Ordering::SeqCst),0);
}
