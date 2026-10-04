use std::time::Duration;
use volna_core::*;

fn route(id: &str, domain: &str, rtt: f64) -> Route {
    Route { id: id.into(), failure_domain: domain.into(), transport: Transport::Awg,
        accepting_connections: true, metrics: Metrics {
            success_probability: 0.99, rtt_ms: rtt, loss: 0.005, jitter_ms: 3.0,
            server_load: 0.2, stability: 0.95, historical_success: 0.99,
            transport_cost: 0.1, battery_cost: 0.1 } }
}
#[test]
fn recovery_requires_ready_backup_and_migration_confirmation() {
    let mut s = StateMachine::default();
    for e in [Event::Start, Event::ProfileReady, Event::CandidatesReady,
        Event::TunnelReady, Event::QualityDropped, Event::PrepareBackup] {
        s.apply(e).unwrap();
    }
    assert!(s.apply(Event::MigrationSucceeded).is_err());
    assert_eq!(s.state(), State::PreparingBackup);
    s.apply(Event::BackupReady).unwrap();
    s.apply(Event::MigrationFailed).unwrap();
    assert_eq!(s.state(), State::Degraded);
    s.apply(Event::NetworkLost).unwrap();
    s.apply(Event::NetworkRestored).unwrap();
    assert_eq!(s.state(), State::Profiling);
}
#[test]
fn race_is_bounded_staggered_and_excludes_draining_or_invalid_routes() {
    let fast = route("fast","a",20.0);
    let slow = route("slow","b",200.0);
    let mut draining = route("draining","c",1.0);
    draining.accepting_connections = false;
    let mut invalid = route("invalid","d",1.0);
    invalid.metrics.loss = f64::NAN;
    let plan = race_plan(&[slow,draining,fast.clone(),fast,invalid],
        Mode::Auto,Duration::from_millis(100),3);
    assert_eq!(plan.len(),2);
    assert_eq!(plan[0].route.id,"fast");
    assert_eq!(plan[1].start_after,Duration::from_millis(100));
    assert!(choose_ready(&plan,100.0,false).is_none());
    assert_eq!(choose_ready(&plan,100.0,true).unwrap().route.id,"fast");
}
#[test]
fn reserve_uses_an_independent_failure_domain() {
    let active = route("active","provider-a",20.0);
    let plan = backup_plan(&[active.clone(),route("same","provider-a",10.0),
        route("reserve","provider-b",40.0)],&active,Mode::Auto);
    assert_eq!(plan.len(),1);
    assert_eq!(plan[0].route.id,"reserve");
}
#[test]
fn noisy_loss_does_not_trigger_prewarm_but_sustained_loss_does() {
    let mut monitor = HealthMonitor::default();
    assert_eq!(monitor.observe_loss(0.0),Some(HealthAction::Keep));
    assert_eq!(monitor.observe_loss(0.17),Some(HealthAction::Keep));
    let mut action = HealthAction::Keep;
    for _ in 0..12 { action = monitor.observe_loss(0.17).unwrap(); }
    assert_eq!(action,HealthAction::PrepareBackup);
    assert_eq!(monitor.observe_loss(f64::INFINITY),None);
    for _ in 0..20 { action = monitor.observe_loss(0.0).unwrap(); }
    assert_eq!(action,HealthAction::Keep);
}
