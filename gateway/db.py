"""SQLite connections, schema, seed data, and lazy expiry."""

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
TOKEN_PATH = ROOT / ".demo_token"
SCHEMA = """
CREATE TABLE IF NOT EXISTS agents (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, token_hash TEXT NOT NULL,
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
def connection():
    conn = sqlite3.connect(os.getenv("DB_PATH", str(ROOT / "spendguard.db")), timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def transaction():
    with connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise


def seed(conn):
    if TOKEN_PATH.exists():
        token = TOKEN_PATH.read_text(encoding="utf-8").strip()
        if not token:
            raise ValueError("demo token file is empty")
    else:
        token = secrets.token_urlsafe(32)
        TOKEN_PATH.write_text(token, encoding="utf-8")
    conn.execute("INSERT INTO agents VALUES (?, ?, ?, 'active')", (
        "research-bot", "Research Bot", hashlib.sha256(token.encode()).hexdigest()))
    conn.execute("INSERT INTO policies VALUES (?, ?, ?, ?, ?)", (
        "research-bot", 50, 100, 25,
        json.dumps(["openai.com", "serpapi.com", "aws.amazon.com"])))
    conn.execute("INSERT OR REPLACE INTO settings VALUES ('kill_switch_global', '0')")


def initialize():
    with connection() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)
    with transaction() as conn:
        if not conn.execute("SELECT 1 FROM agents LIMIT 1").fetchone():
            seed(conn)


def expire(conn, timestamp: str):
    conn.execute("""UPDATE requests SET status='expired', decided_at=?,
                    decision_reason='approval expired'
                    WHERE status='pending_approval' AND expires_at<=?""",
                 (timestamp, timestamp))


def killed(conn) -> bool:
    row = conn.execute("SELECT value FROM settings WHERE key='kill_switch_global'").fetchone()
    return row is None or row["value"] != "0"
