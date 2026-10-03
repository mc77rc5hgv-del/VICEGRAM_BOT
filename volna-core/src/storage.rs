//! Single-writer Unix cache in an application-owned private directory.
use std::{fs::{File,OpenOptions},io::{Read,Write},
    os::unix::fs::{MetadataExt,OpenOptionsExt},path::{Path,PathBuf},time::Duration};
use fs2::FileExt;
use serde::{Deserialize,Serialize};
use crate::config::{ConfigStore,ConfigError,Envelope,LoadedConfig,Verifier,MAX_ENVELOPE};

#[derive(Debug,PartialEq,Eq)]
pub enum StorageError { Permissions,Locked,Missing,Exists,Corrupt,Io,Poisoned,Config(ConfigError) }
#[derive(Serialize,Deserialize)]
#[serde(deny_unknown_fields)]
struct Record { schema: u32,floor: u64,last_time: u64,envelope: Option<Envelope> }
pub struct PersistentConfigStore {
    store: ConfigStore,path: PathBuf,_lock: File,poisoned: bool,
}
fn owned_private(m: &std::fs::Metadata,directory: bool) -> bool {
    // SAFETY: geteuid has no pointer arguments or side effects.
    let uid = unsafe { libc::geteuid() };
    m.uid() == uid && m.mode() & 0o077 == 0
        && if directory { m.is_dir() } else { m.is_file() && m.nlink() == 1 }
}
fn check_parent(path: &Path) -> Result<(),StorageError> {
    if !path.is_absolute() || path.file_name().is_none() { return Err(StorageError::Permissions); }
    let m = std::fs::symlink_metadata(path.parent().ok_or(StorageError::Permissions)?)
        .map_err(|_| StorageError::Permissions)?;
    if !owned_private(&m,true) || m.file_type().is_symlink() {
        return Err(StorageError::Permissions);
    }
    Ok(())
}
fn open_private(path: &Path,create: bool) -> Result<File,StorageError> {
    let file = OpenOptions::new().read(true).write(create).create(create)
        .mode(0o600).custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(path).map_err(|e| if e.kind() == std::io::ErrorKind::NotFound {
            StorageError::Missing } else { StorageError::Io })?;
    if !owned_private(&file.metadata().map_err(|_| StorageError::Io)?,false) {
        return Err(StorageError::Permissions);
    }
    Ok(file)
}
fn lock(path: &Path) -> Result<File,StorageError> {
    check_parent(path)?;
    let lock_path = path.with_extension("lock");
    if lock_path == path { return Err(StorageError::Permissions); }
    let file = open_private(&lock_path,true)?;
    file.try_lock_exclusive().map_err(|_| StorageError::Locked)?;
    Ok(file)
}
fn record(store: &ConfigStore) -> Record {
    Record { schema: 1,floor: store.version_floor(),
        last_time: store.last_observed_time(),envelope: store.snapshot() }
}
fn write_atomic(path: &Path,record: &Record,initial: bool) -> Result<(),StorageError> {
    check_parent(path)?;
    if !initial { drop(open_private(path,false)?); }
    let parent = path.parent().ok_or(StorageError::Permissions)?;
    let bytes = serde_json::to_vec(record).map_err(|_| StorageError::Io)?;
    if bytes.len() > MAX_ENVELOPE+4096 { return Err(StorageError::Corrupt); }
    let mut temp = tempfile::NamedTempFile::new_in(parent).map_err(|_| StorageError::Io)?;
    temp.write_all(&bytes).map_err(|_| StorageError::Io)?;
    temp.flush().map_err(|_| StorageError::Io)?;
    temp.as_file().sync_all().map_err(|_| StorageError::Io)?;
    if initial {
        temp.persist_noclobber(path).map_err(|e|
            if e.error.kind() == std::io::ErrorKind::AlreadyExists {
                StorageError::Exists } else { StorageError::Io })?;
    } else { temp.persist(path).map_err(|_| StorageError::Io)?; }
    File::open(parent).and_then(|dir| dir.sync_all()).map_err(|_| StorageError::Io)?;
    Ok(())
}
impl PersistentConfigStore {
    /// Explicit first-install initialization. Never silently resets existing state.
    pub fn create(path: PathBuf,verifier: Verifier,minimum_version: u64,
        minimum_time: u64,grace: Duration) -> Result<Self,StorageError> {
        let lock = lock(&path)?;
        let store = ConfigStore::new(verifier,minimum_version,minimum_time,grace);
        write_atomic(&path,&record(&store),true)?;
        Ok(Self { store,path,_lock: lock,poisoned: false })
    }
    pub fn open(path: PathBuf,verifier: Verifier,minimum_version: u64,
        minimum_time: u64,grace: Duration,now: u64) -> Result<Self,StorageError> {
        let lock = lock(&path)?;
        let mut file = open_private(&path,false)?;
        if file.metadata().map_err(|_| StorageError::Io)?.len() > MAX_ENVELOPE as u64 + 4096 {
            return Err(StorageError::Corrupt);
        }
        let mut bytes = Vec::new();
        (&mut file).take((MAX_ENVELOPE+4097) as u64).read_to_end(&mut bytes)
            .map_err(|_| StorageError::Io)?;
        if bytes.len() > MAX_ENVELOPE+4096 { return Err(StorageError::Corrupt); }
        let saved: Record = serde_json::from_slice(&bytes).map_err(|_| StorageError::Corrupt)?;
        if saved.schema != 1 || saved.floor < minimum_version
            || saved.last_time < minimum_time { return Err(StorageError::Corrupt); }
        let mut store = ConfigStore::new(verifier.clone(),saved.floor,saved.last_time,grace);
        if let Some(envelope) = saved.envelope {
            let verified = verifier.verify(envelope.clone()).map_err(StorageError::Config)?;
            if verified.manifest().version != saved.floor { return Err(StorageError::Corrupt); }
            store.restore(envelope,now).map_err(StorageError::Config)?;
        } else if now < saved.last_time {
            return Err(StorageError::Config(ConfigError::ClockRollback));
        }
        Ok(Self { store,path,_lock: lock,poisoned: false })
    }
    pub fn version_floor(&self) -> u64 { self.store.version_floor() }
    fn commit(&mut self,candidate: ConfigStore) -> Result<(),StorageError> {
        if self.poisoned { return Err(StorageError::Poisoned); }
        if let Err(error) = write_atomic(&self.path,&record(&candidate),false) {
            // Rename could succeed before directory fsync fails. Require reopen.
            self.poisoned = true;
            return Err(error);
        }
        self.store = candidate;
        Ok(())
    }
    pub fn accept(&mut self,envelope: Envelope,now: u64) -> Result<LoadedConfig,StorageError> {
        if self.poisoned { return Err(StorageError::Poisoned); }
        let mut candidate = self.store.clone();
        let loaded = candidate.accept(envelope,now).map_err(StorageError::Config)?;
        self.commit(candidate)?;
        Ok(loaded)
    }
    pub fn cache(&mut self,now: u64) -> Result<LoadedConfig,StorageError> {
        if self.poisoned { return Err(StorageError::Poisoned); }
        let mut candidate = self.store.clone();
        let result = candidate.cache(now);
        // Persist clock progress even when cache expires.
        self.commit(candidate)?;
        result.map_err(StorageError::Config)
    }
}
