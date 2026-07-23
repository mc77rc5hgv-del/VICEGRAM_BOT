import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from config import settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS peers (
    telegram_id   INTEGER PRIMARY KEY,
    telegram_name TEXT,
    ip_address    TEXT NOT NULL UNIQUE,
    public_key    TEXT NOT NULL UNIQUE,
    private_key   TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    revoked_at    TEXT
);
"""


@contextmanager
def _connect():
    Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _connect() as conn:
        conn.execute(_SCHEMA)


@dataclass
class Peer:
    telegram_id: int
    telegram_name: str | None
    ip_address: str
    public_key: str
    private_key: str
    created_at: str
    revoked_at: str | None

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None


def _row_to_peer(row: sqlite3.Row) -> Peer:
    return Peer(**dict(row))


def get_active_peer(telegram_id: int) -> Peer | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM peers WHERE telegram_id = ? AND revoked_at IS NULL",
            (telegram_id,),
        ).fetchone()
        return _row_to_peer(row) if row else None


def used_ips() -> set[str]:
    with _connect() as conn:
        rows = conn.execute("SELECT ip_address FROM peers WHERE revoked_at IS NULL").fetchall()
        return {r["ip_address"] for r in rows}


def create_peer(telegram_id: int, telegram_name: str | None, ip_address: str,
                 public_key: str, private_key: str) -> Peer:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            """INSERT INTO peers (telegram_id, telegram_name, ip_address, public_key,
                                   private_key, created_at, revoked_at)
               VALUES (?, ?, ?, ?, ?, ?, NULL)
               ON CONFLICT(telegram_id) DO UPDATE SET
                 telegram_name=excluded.telegram_name,
                 ip_address=excluded.ip_address,
                 public_key=excluded.public_key,
                 private_key=excluded.private_key,
                 created_at=excluded.created_at,
                 revoked_at=NULL""",
            (telegram_id, telegram_name, ip_address, public_key, private_key, now),
        )
    peer = get_active_peer(telegram_id)
    assert peer is not None
    return peer


def revoke_peer(telegram_id: int) -> Peer | None:
    peer = get_active_peer(telegram_id)
    if peer is None:
        return None
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            "UPDATE peers SET revoked_at = ? WHERE telegram_id = ?",
            (now, telegram_id),
        )
    return peer


def stats() -> dict:
    with _connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM peers WHERE revoked_at IS NULL").fetchone()[0]
        revoked = conn.execute("SELECT COUNT(*) FROM peers WHERE revoked_at IS NOT NULL").fetchone()[0]
    return {"active": total, "revoked": revoked}


def list_active_peers(limit: int = 50, offset: int = 0) -> list[Peer]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM peers WHERE revoked_at IS NULL ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [_row_to_peer(r) for r in rows]
