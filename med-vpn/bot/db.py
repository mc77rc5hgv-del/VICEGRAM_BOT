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
    username      TEXT NOT NULL UNIQUE,
    password      TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    revoked_at    TEXT
);

CREATE TABLE IF NOT EXISTS users (
    telegram_id   INTEGER PRIMARY KEY,
    telegram_name TEXT,
    referred_by   INTEGER,
    balance       REAL NOT NULL DEFAULT 0,
    joined_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS purchases (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id  INTEGER NOT NULL,
    amount       REAL NOT NULL,
    currency     TEXT NOT NULL,
    commission   REAL NOT NULL,
    referrer_id  INTEGER,
    created_at   TEXT NOT NULL
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
        conn.executescript(_SCHEMA)


@dataclass
class Client:
    telegram_id: int
    telegram_name: str | None
    username: str
    password: str
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


def create_client(telegram_id: int, telegram_name: str | None, username: str, password: str) -> Client:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            """INSERT INTO clients (telegram_id, telegram_name, username, password, created_at, revoked_at)
               VALUES (?, ?, ?, ?, ?, NULL)
               ON CONFLICT(telegram_id) DO UPDATE SET
                 telegram_name=excluded.telegram_name,
                 username=excluded.username,
                 password=excluded.password,
                 created_at=excluded.created_at,
                 revoked_at=NULL""",
            (telegram_id, telegram_name, username, password, now),
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


@dataclass
class User:
    telegram_id: int
    telegram_name: str | None
    referred_by: int | None
    balance: float
    joined_at: str


def _row_to_user(row: sqlite3.Row) -> User:
    return User(**dict(row))


def get_user(telegram_id: int) -> User | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
        return _row_to_user(row) if row else None


def get_or_create_user(telegram_id: int, telegram_name: str | None, referred_by: int | None = None) -> User:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            """INSERT INTO users (telegram_id, telegram_name, referred_by, balance, joined_at)
               VALUES (?, ?, ?, 0, ?)
               ON CONFLICT(telegram_id) DO UPDATE SET telegram_name=excluded.telegram_name""",
            (telegram_id, telegram_name, referred_by, now),
        )
    user = get_user(telegram_id)
    assert user is not None
    return user


def referral_stats(telegram_id: int) -> dict:
    with _connect() as conn:
        invited = conn.execute(
            "SELECT COUNT(*) FROM users WHERE referred_by = ?", (telegram_id,)
        ).fetchone()[0]
        row = conn.execute("SELECT balance FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
    return {"invited": invited, "balance": row["balance"] if row else 0.0}


def record_purchase(telegram_id: int, amount: float, currency: str) -> dict:
    user = get_user(telegram_id)
    referrer_id = user.referred_by if user else None
    commission = round(amount * settings.referral_commission_rate, 2) if referrer_id else 0.0
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            """INSERT INTO purchases (telegram_id, amount, currency, commission, referrer_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (telegram_id, amount, currency, commission, referrer_id, now),
        )
        if referrer_id and commission > 0:
            conn.execute(
                """INSERT INTO users (telegram_id, telegram_name, referred_by, balance, joined_at)
                   VALUES (?, NULL, NULL, ?, ?)
                   ON CONFLICT(telegram_id) DO UPDATE SET balance = balance + ?""",
                (referrer_id, commission, now, commission),
            )
    return {"referrer_id": referrer_id, "commission": commission}


def payout_balance(telegram_id: int) -> float:
    user = get_user(telegram_id)
    amount = user.balance if user else 0.0
    with _connect() as conn:
        conn.execute("UPDATE users SET balance = 0 WHERE telegram_id = ?", (telegram_id,))
    return amount
