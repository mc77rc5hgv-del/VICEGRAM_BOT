//! Linux TUN profiles and explicit fail-closed routing policy.
//! Requires a trusted iproute2 executable and an isolated/owned routing scope.
use std::{ffi::CString,path::PathBuf,process::Stdio,time::Duration};
use serde_json::{json,Value};
use tokio::{process::Command,time::timeout};
pub const TRANSPORT_MARK: u32 = 0x564f;
#[derive(Clone)]
pub struct TunProfile { interface: String,slot: u8 }
#[derive(Debug,PartialEq,Eq)]
pub enum TunError { Invalid,Privilege,Conflict,Command,Rollback }
impl TunProfile {
    pub fn new(interface: String,slot: u8) -> Result<Self,TunError> {
        if !interface.starts_with("volna") || interface.len() > 15 || slot == 0 || slot > 64
            || !interface.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'_' || b == b'-') {
            return Err(TunError::Invalid);
        }
        Ok(Self { interface,slot })
    }
    pub fn interface(&self) -> &str { &self.interface }
    pub fn slot(&self) -> u8 { self.slot }
    pub(crate) fn config(&self) -> Value {
        json!({"name": self.interface,"mtu": 1400,
            "address": {"ipv4": format!("100.64.{}.1/30",self.slot),
                "ipv6": format!("fd00:564f:{}::1/126",self.slot)}})
    }
}
pub fn interface_exists(name: &str) -> bool {
    let Ok(name) = CString::new(name) else { return false };
    // SAFETY: NUL-terminated name remains alive for the call.
    unsafe { libc::if_nametoindex(name.as_ptr()) != 0 }
}
pub struct LinuxPolicyRouter {
    ip: PathBuf,table: String,priority: u32,active: Option<String>,installed: bool,
}
impl LinuxPolicyRouter {
    async fn command(&self,args: Vec<String>) -> Result<Vec<u8>,TunError> {
        let output = timeout(Duration::from_secs(2),Command::new(&self.ip)
            .args(args).env_clear().stdin(Stdio::null()).stderr(Stdio::null())
            .kill_on_drop(true).output()).await.map_err(|_| TunError::Command)?
            .map_err(|_| TunError::Command)?;
        if !output.status.success() { return Err(TunError::Command); }
        Ok(output.stdout)
    }
    fn route_args(&self,family: &str,operation: &str,device: Option<&str>) -> Vec<String> {
        let mut args = vec![family.into(),"route".into(),operation.into(),"table".into(),
            self.table.clone()];
        if let Some(device) = device {
            args.extend(["default".into(),"dev".into(),device.into(),"metric".into(),"10".into()]);
        } else {
            args.extend(["blackhole".into(),"default".into(),"metric".into(),"32767".into()]);
        }
        args
    }
    /// Table and rule priorities must be reserved by the platform. Existing entries
    /// are rejected. Current namespace is the scope; no network namespace is selected.
    pub async fn install(ip: PathBuf,table: u32,priority: u32) -> Result<Self,TunError> {
        if !ip.is_absolute() || !ip.is_file() || !(1000..=60000).contains(&table)
            || !(10000..=30000).contains(&priority) { return Err(TunError::Invalid); }
        // SAFETY: geteuid has no pointer arguments or side effects.
        if unsafe { libc::geteuid() } != 0 { return Err(TunError::Privilege); }
        let router = Self { ip,table: table.to_string(),priority,active: None,installed: true };
        for family in ["-4","-6"] {
            let rules = router.command(vec![family.into(),"-j".into(),"rule".into(),"show".into()]).await?;
            let rules: Vec<Value> = serde_json::from_slice(&rules).map_err(|_| TunError::Command)?;
            if rules.iter().any(|r| r["priority"].as_u64().is_some_and(|p|
                p == priority as u64 || p == priority as u64+1)) { return Err(TunError::Conflict); }
            // iproute2 returns an error for a never-created table. Inspect all tables
            // instead, keeping absence distinct from failures.
            let routes = router.command(vec![family.into(),"-j".into(),"route".into(),
                "show".into(),"table".into(),"all".into()]).await?;
            let routes: Vec<Value> = serde_json::from_slice(&routes).map_err(|_| TunError::Command)?;
            if routes.iter().any(|r| r["table"].as_u64() == Some(table as u64)
                || r["table"].as_str() == Some(router.table.as_str())) {
                return Err(TunError::Conflict);
            }
        }
        let mut changes: Vec<(Vec<String>,Vec<String>)> = Vec::new();
        for family in ["-4","-6"] {
            changes.push((router.route_args(family,"add",None),router.route_args(family,"del",None)));
            for (pref,rule) in [(priority,vec!["fwmark".into(),TRANSPORT_MARK.to_string(),"lookup".into(),"main".into()]),
                (priority+1,vec!["lookup".into(),router.table.clone()])] {
                let mut add = vec![family.into(),"rule".into(),"add".into(),"priority".into(),pref.to_string()];
                add.extend(rule);
                let remove = vec![family.into(),"rule".into(),"del".into(),"priority".into(),pref.to_string()];
                changes.push((add,remove));
            }
        }
        let mut applied: Vec<Vec<String>> = Vec::new();
        for (add,remove) in changes {
            if let Err(error) = router.command(add).await {
                for undo in applied.into_iter().rev() {
                    if router.command(undo).await.is_err() { return Err(TunError::Rollback); }
                }
                return Err(error);
            }
            applied.push(remove);
        }
        Ok(router)
    }
    pub async fn activate(&mut self,profile: &TunProfile) -> Result<(),TunError> {
        if !self.installed || !interface_exists(profile.interface()) { return Err(TunError::Invalid); }
        self.command(self.route_args("-4","replace",Some(profile.interface()))).await?;
        if self.command(self.route_args("-6","replace",Some(profile.interface()))).await.is_err() {
            let undo = if let Some(old) = &self.active {
                self.route_args("-4","replace",Some(old))
            } else { vec!["-4".into(),"route".into(),"del".into(),"table".into(),
                self.table.clone(),"default".into(),"metric".into(),"10".into()] };
            self.command(undo).await.map_err(|_| TunError::Rollback)?;
            return Err(TunError::Command);
        }
        self.active = Some(profile.interface().to_string());
        Ok(())
    }
    /// Explicit user disconnect restores ordinary routing. Drop intentionally leaves
    /// guards installed so a supervisor/process crash does not enable direct traffic.
    pub async fn disconnect(&mut self) -> Result<(),TunError> {
        if !self.installed { return Ok(()); }
        for family in ["-4","-6"] {
            for priority in [self.priority+1,self.priority] {
                self.command(vec![family.into(),"rule".into(),"del".into(),
                    "priority".into(),priority.to_string()]).await?;
            }
            self.command(vec![family.into(),"route".into(),"flush".into(),"table".into(),
                self.table.clone()]).await?;
        }
        self.installed = false; self.active = None;
        Ok(())
    }
}

/// Activates only the TUN interface owned by the selected authenticated session.
/// Router ownership remains with the caller; cancellation never disconnects it.
pub struct HysteriaTunActivator<'a> { pub router: &'a mut LinuxPolicyRouter }
impl crate::supervisor::PathActivator<crate::hysteria::HysteriaSession> for HysteriaTunActivator<'_> {
    fn activate<'a>(&'a mut self,session: &'a crate::hysteria::HysteriaSession)
        -> crate::supervisor::ActivationFuture<'a> {
        Box::pin(async move {
            let interface = session.tun_interface().ok_or(())?;
            // Address slot does not affect activation; interface comes from the
            // validated connector profile rather than remote input.
            let profile = TunProfile::new(interface.to_string(),1).map_err(|_| ())?;
            self.router.activate(&profile).await.map_err(|_| ())
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn profiles_validate_and_disable_auto_routes() {
        for (name,slot) in [("eth0",1),("volna/evil",1),("volna0",0),("volna0",65)] {
            assert!(TunProfile::new(name.into(),slot).is_err());
        }
        let p = TunProfile::new("volna0".into(),1).unwrap();
        assert_eq!(p.config()["address"]["ipv4"],"100.64.1.1/30");
        assert!(p.config().get("route").is_none());
    }
}

