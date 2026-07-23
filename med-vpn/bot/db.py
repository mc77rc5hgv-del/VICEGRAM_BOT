import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from config import settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (
    telegram_id   INTEGER PRIMARY KEY,
    telegram_name TEXT,
    uuid          TEXT NOT NULL UNIQUE,
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
class Client:
    telegram_id: int
    telegram_name: str | None
    uuid: str
    created_at: str
    revoked_at: str | None

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None


def _row_to_client(row: sqlite3.Row) -> Client:
    return Client(**dict(row))


def get_active_client(telegram_id: int) -> Client | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM clients WHERE telegram_id = ? AND revoked_at IS NULL",
            (telegram_id,),
        ).fetchone()
        return _row_to_client(row) if row else None


def create_client(telegram_id: int, telegram_name: str | None, client_uuid: str) -> Client:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            """INSERT INTO clients (telegram_id, telegram_name, uuid, created_at, revoked_at)
               VALUES (?, ?, ?, ?, NULL)
               ON CONFLICT(telegram_id) DO UPDATE SET
                 telegram_name=excluded.telegram_name,
                 uuid=excluded.uuid,
                 created_at=excluded.created_at,
                 revoked_at=NULL""",
            (telegram_id, telegram_name, client_uuid, now),
        )
    client = get_active_client(telegram_id)
    assert client is not None
    return client


def revoke_client(telegram_id: int) -> Client | None:
    client = get_active_client(telegram_id)
    if client is None:
        return None
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            "UPDATE clients SET revoked_at = ? WHERE telegram_id = ?",
            (now, telegram_id),
        )
    return client


def stats() -> dict:
    with _connect() as conn:
        active = conn.execute("SELECT COUNT(*) FROM clients WHERE revoked_at IS NULL").fetchone()[0]
        revoked = conn.execute("SELECT COUNT(*) FROM clients WHERE revoked_at IS NOT NULL").fetchone()[0]
    return {"active": active, "revoked": revoked}


def list_active_clients(limit: int = 50, offset: int = 0) -> list[Client]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM clients WHERE revoked_at IS NULL ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [_row_to_client(r) for r in rows]
