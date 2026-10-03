use std::{sync::{Arc,atomic::{AtomicUsize,Ordering}},time::Duration};
use tokio::sync::watch;
use volna_core::{*,runtime::*,supervisor::*};
struct Fake { checks: AtomicUsize,closed: Arc<AtomicUsize>,reject_backup: bool }
struct Session { id: String,closed: Arc<AtomicUsize> }
impl Drop for Session { fn drop(&mut self) { self.closed.fetch_add(1,Ordering::SeqCst); } }
impl Connector for Fake {
    type Session = Session;
    fn supports(&self,_: Transport) -> bool { true }
    fn connect<'a>(&'a self,a: &'a Attempt) -> ConnectFuture<'a,Session> {
        Box::pin(async move {
            if a.route.id == "b" && self.reject_backup { return Err(ConnectError::Authentication); }
            Ok(Session { id: a.route.id.clone(),closed: self.closed.clone() })
        })
    }
}
impl MonitoredConnector for Fake {
    type Handle = String;
    fn handle(&self,s: &Session) -> String { s.id.clone() }
    fn health<'a>(&'a self,s: &'a mut Session) -> HealthFuture<'a> {
        Box::pin(async move {
            if s.id == "a" {
                let calls = self.checks.fetch_add(1,Ordering::SeqCst);
                if calls >= 1 { return Err(()); }
                Ok(HealthSample { rtt: Duration::from_secs(1) })
            } else { Ok(HealthSample { rtt: Duration::from_millis(10) }) }
        })
    }
}
fn route(id: &str,rtt: f64) -> Route {
    Route { id: id.into(),failure_domain: id.into(),transport: Transport::Hysteria2,
        accepting_connections: true,metrics: Metrics { success_probability: 1.0,
            rtt_ms: rtt,loss: 0.0,jitter_ms: 0.0,server_load: 0.0,stability: 1.0,
            historical_success: 1.0,transport_cost: 0.0,battery_cost: 0.0 } }
}
fn options() -> SupervisorOptions {
    SupervisorOptions { interval: Duration::from_millis(100),degraded_samples: 1,
        cooldown: Duration::ZERO,..SupervisorOptions::default() }
}
#[tokio::test(start_paused=true)]
async fn prewarm_switch_and_generation_cancel_close_all_sessions() {
    let closed = Arc::new(AtomicUsize::new(0));
    let c = Arc::new(Fake { checks: AtomicUsize::new(0),closed: closed.clone(),reject_backup: false });
    let (epoch_tx,epoch_rx) = watch::channel(1);
    let (active_tx,active_rx) = watch::channel(None);
    let (status_tx,mut status_rx) = watch::channel(SupervisorStatus::default());
    let task = tokio::spawn(supervise(c,vec![route("a",1.0),route("b",500.0)],
        Mode::Auto,options(),SupervisorChannels { generation: epoch_rx,
            active: active_tx,status: status_tx },1));
    timeout_switch(&mut status_rx).await;
    assert_eq!(active_rx.borrow().as_ref().unwrap().route_id,"b");
    assert_eq!(closed.load(Ordering::SeqCst),1);
    epoch_tx.send(2).unwrap();
    assert_eq!(task.await.unwrap(),Err(SupervisorError::Cancelled));
    assert!(active_rx.borrow().is_none());
    assert_eq!(closed.load(Ordering::SeqCst),2);
}
async fn timeout_switch(rx: &mut watch::Receiver<SupervisorStatus>) {
    tokio::time::timeout(Duration::from_secs(3),async {
        loop {
            if rx.borrow().switches > 0 { break; }
            rx.changed().await.unwrap();
        }
    }).await.unwrap();
}
#[tokio::test(start_paused=true)]
async fn failed_reserve_never_publishes_connected_backup() {
    let closed = Arc::new(AtomicUsize::new(0));
    let c = Arc::new(Fake { checks: AtomicUsize::new(0),closed: closed.clone(),reject_backup: true });
    let (_epoch_tx,epoch_rx) = watch::channel(1);
    let (active_tx,active_rx) = watch::channel(None);
    let (status_tx,status_rx) = watch::channel(SupervisorStatus::default());
    let result = supervise(c,vec![route("a",1.0),route("b",500.0)],
        Mode::Auto,options(),SupervisorChannels { generation: epoch_rx,
            active: active_tx,status: status_tx },1).await;
    assert_eq!(result,Err(SupervisorError::Unavailable));
    assert!(active_rx.borrow().is_none());
    assert_eq!(status_rx.borrow().state,State::Failed);
    assert_eq!(closed.load(Ordering::SeqCst),1);
}
#[tokio::test(start_paused=true)]
async fn dropping_supervisor_unpublishes_active_path() {
    let closed = Arc::new(AtomicUsize::new(0));
    let c = Arc::new(Fake { checks: AtomicUsize::new(0),closed: closed.clone(),reject_backup: false });
    let (_epoch_tx,epoch_rx) = watch::channel(1);
    let (active_tx,active_rx) = watch::channel(None);
    let (status_tx,mut status_rx) = watch::channel(SupervisorStatus::default());
    let task = tokio::spawn(supervise(c,vec![route("a",1.0),route("b",500.0)],
        Mode::Auto,options(),SupervisorChannels { generation: epoch_rx,
            active: active_tx,status: status_tx },1));
    loop { if active_rx.borrow().is_some() { break; } status_rx.changed().await.unwrap(); }
    task.abort();
    assert!(task.await.unwrap_err().is_cancelled());
    assert!(active_rx.borrow().is_none());
    assert!(closed.load(Ordering::SeqCst) >= 1);
}

struct ActivationCheck {
    active: watch::Receiver<Option<ActivePath<String>>>,
    closed: Arc<AtomicUsize>,calls: Arc<AtomicUsize>,reject_backup: bool,
}
impl PathActivator<Session> for ActivationCheck {
    fn activate<'a>(&'a mut self,s: &'a Session) -> ActivationFuture<'a> {
        Box::pin(async move {
            assert_eq!(self.closed.load(Ordering::SeqCst),0,"old session must remain alive during activation");
            if s.id == "a" { assert!(self.active.borrow().is_none()); }
            else { assert_eq!(self.active.borrow().as_ref().unwrap().route_id,"a"); }
            self.calls.fetch_add(1,Ordering::SeqCst);
            if s.id == "b" && self.reject_backup { Err(ActivationError::Fatal) } else { Ok(()) }
        })
    }
}
#[tokio::test(start_paused=true)]
async fn activation_precedes_publication_and_old_session_drop() {
    let closed = Arc::new(AtomicUsize::new(0));
    let calls = Arc::new(AtomicUsize::new(0));
    let c = Arc::new(Fake { checks: AtomicUsize::new(0),closed: closed.clone(),reject_backup: false });
    let (tx,rx) = watch::channel(1);
    let (active_tx,active_rx) = watch::channel(None);
    let (status_tx,mut status_rx) = watch::channel(SupervisorStatus::default());
    let mut activation = ActivationCheck { active: active_rx.clone(),closed: closed.clone(),
        calls: calls.clone(),reject_backup: false };
    let task = tokio::spawn(async move {
        supervise_with_activation(c,vec![route("a",1.0),route("b",500.0)],Mode::Auto,
            options(),SupervisorChannels { generation: rx,active: active_tx,status: status_tx },
            1,&mut activation).await
    });
    timeout_switch(&mut status_rx).await;
    assert_eq!(calls.load(Ordering::SeqCst),2);
    assert_eq!(active_rx.borrow().as_ref().unwrap().route_id,"b");
    tx.send(2).unwrap();
    assert_eq!(task.await.unwrap(),Err(SupervisorError::Cancelled));
    assert_eq!(closed.load(Ordering::SeqCst),2);
}
#[tokio::test(start_paused=true)]
async fn failed_activation_never_publishes_backup_and_closes_sessions() {
    let closed = Arc::new(AtomicUsize::new(0));
    let calls = Arc::new(AtomicUsize::new(0));
    let c = Arc::new(Fake { checks: AtomicUsize::new(0),closed: closed.clone(),reject_backup: false });
    let (_tx,rx) = watch::channel(1);
    let (active_tx,active_rx) = watch::channel(None);
    let (status_tx,status_rx) = watch::channel(SupervisorStatus::default());
    let mut activation = ActivationCheck { active: active_rx.clone(),closed: closed.clone(),
        calls: calls.clone(),reject_backup: true };
    let result = supervise_with_activation(c,vec![route("a",1.0),route("b",500.0)],
        Mode::Auto,options(),SupervisorChannels { generation: rx,active: active_tx,status: status_tx },
        1,&mut activation).await;
    assert_eq!(result,Err(SupervisorError::Activation));
    assert_eq!(calls.load(Ordering::SeqCst),2);
    assert!(active_rx.borrow().is_none());
    assert_eq!(status_rx.borrow().state,State::Failed);
    assert_eq!(closed.load(Ordering::SeqCst),2);
}

struct CancelActivation {
    epoch: watch::Sender<u64>,active: watch::Receiver<Option<ActivePath<String>>>,
}
impl PathActivator<Session> for CancelActivation {
    fn activate<'a>(&'a mut self,_s: &'a Session) -> ActivationFuture<'a> {
        Box::pin(async move {
            self.epoch.send(2).unwrap();
            tokio::time::sleep(Duration::from_millis(10)).await;
            assert!(self.active.borrow().is_none(),"cancelled epoch must never publish Connected");
            Ok(())
        })
    }
}
#[tokio::test(start_paused=true)]
async fn epoch_change_during_activation_finishes_without_publication() {
    let closed = Arc::new(AtomicUsize::new(0));
    let c = Arc::new(Fake { checks: AtomicUsize::new(0),closed: closed.clone(),reject_backup: false });
    let (tx,rx) = watch::channel(1);
    let (active_tx,active_rx) = watch::channel(None);
    let (status_tx,status_rx) = watch::channel(SupervisorStatus::default());
    let mut activation = CancelActivation { epoch: tx,active: active_rx.clone() };
    let result = supervise_with_activation(c,vec![route("a",1.0)],Mode::Auto,
        options(),SupervisorChannels { generation: rx,active: active_tx,status: status_tx },
        1,&mut activation).await;
    assert_eq!(result,Err(SupervisorError::Cancelled));
    assert!(active_rx.borrow().is_none());
    assert_eq!(status_rx.borrow().state,State::Idle);
    assert_eq!(closed.load(Ordering::SeqCst),1);
}

struct RetryActivation {
    active: watch::Receiver<Option<ActivePath<String>>>,closed: Arc<AtomicUsize>,
    attempts: Arc<AtomicUsize>,
}
impl PathActivator<Session> for RetryActivation {
    fn activate<'a>(&'a mut self,s: &'a Session) -> ActivationFuture<'a> {
        Box::pin(async move {
            if s.id == "b" {
                assert_eq!(self.active.borrow().as_ref().unwrap().route_id,"a");
                assert_eq!(self.closed.load(Ordering::SeqCst),0);
                if self.attempts.fetch_add(1,Ordering::SeqCst) == 0 {
                    return Err(ActivationError::Retryable);
                }
            }
            Ok(())
        })
    }
}
#[tokio::test(start_paused=true)]
async fn restored_activation_retries_without_retiring_or_publishing_backup_early() {
    let closed = Arc::new(AtomicUsize::new(0));
    let attempts = Arc::new(AtomicUsize::new(0));
    let c = Arc::new(Fake { checks: AtomicUsize::new(0),closed: closed.clone(),reject_backup: false });
    let (tx,rx) = watch::channel(1);
    let (active_tx,active_rx) = watch::channel(None);
    let (status_tx,mut status_rx) = watch::channel(SupervisorStatus::default());
    let mut activation = RetryActivation { active: active_rx.clone(),closed: closed.clone(),
        attempts: attempts.clone() };
    let task = tokio::spawn(async move {
        let mut o = options(); o.retry_delay = Duration::from_millis(200);
        supervise_with_activation(c,vec![route("a",1.0),route("b",500.0)],Mode::Auto,o,
            SupervisorChannels { generation: rx,active: active_tx,status: status_tx },1,&mut activation).await
    });
    timeout_switch(&mut status_rx).await;
    assert_eq!(attempts.load(Ordering::SeqCst),2);
    assert_eq!(closed.load(Ordering::SeqCst),1);
    tx.send(2).unwrap();
    assert_eq!(task.await.unwrap(),Err(SupervisorError::Cancelled));
}
