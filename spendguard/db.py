"""Per-operation SQLite connections, schema creation, and lazy expiry."""

from contextlib import contextmanager
from datetime import datetime, timezone
import sqlite3

from spendguard.errors import SpendGuardError

SCHEMA = """
CREATE TABLE IF NOT EXISTS agents (
 id TEXT PRIMARY KEY, name TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'active');
CREATE TABLE IF NOT EXISTS policies (
 agent_id TEXT PRIMARY KEY REFERENCES agents(id), daily_budget REAL NOT NULL,
 per_txn_cap REAL NOT NULL, approval_threshold REAL NOT NULL, allowlist TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS requests (
 id INTEGER PRIMARY KEY AUTOINCREMENT, idempotency_key TEXT NOT NULL UNIQUE,
 agent_id TEXT NOT NULL REFERENCES agents(id), merchant TEXT NOT NULL,
 amount REAL NOT NULL, reason TEXT, status TEXT NOT NULL, decision_reason TEXT,
 explanation TEXT, receipt_id TEXT, approver TEXT, created_at TEXT NOT NULL,
 decided_at TEXT, expires_at TEXT);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@contextmanager
def connection(db_path):
    conn = sqlite3.connect(db_path, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def transaction(db_path):
    with connection(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise


def initialize(db_path):
    with connection(db_path) as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(agents)")}
        if columns and columns != {"id", "name", "status"}:
            raise SpendGuardError("incompatible database schema; use a new database path and keep the old file")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)
    with transaction(db_path) as conn:
        conn.execute("INSERT OR IGNORE INTO settings VALUES ('kill_switch_global', '0')")


def expire(conn, timestamp: str):
    conn.execute("""UPDATE requests SET status='expired', decided_at=?,
                    decision_reason='approval expired'
                    WHERE status='pending_approval' AND expires_at<=?""",
                 (timestamp, timestamp))


def killed(conn) -> bool:
    row = conn.execute("SELECT value FROM settings WHERE key='kill_switch_global'").fetchone()
    return row is None or row["value"] != "0"
