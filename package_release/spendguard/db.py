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
CREATE TABLE IF NOT EXISTS tool_calls (
 request_id INTEGER PRIMARY KEY REFERENCES requests(id) ON DELETE CASCADE,
 tool_name TEXT NOT NULL, arguments TEXT NOT NULL, result TEXT);
CREATE TABLE IF NOT EXISTS teams (id TEXT PRIMARY KEY, name TEXT NOT NULL, daily_budget REAL NOT NULL);
CREATE TABLE IF NOT EXISTS team_members (
 agent_id TEXT PRIMARY KEY REFERENCES agents(id), team_id TEXT NOT NULL REFERENCES teams(id));
CREATE TABLE IF NOT EXISTS request_teams (
 request_id INTEGER PRIMARY KEY REFERENCES requests(id) ON DELETE CASCADE,
 team_id TEXT NOT NULL REFERENCES teams(id));
CREATE TABLE IF NOT EXISTS traces (
 id TEXT PRIMARY KEY, agent_id TEXT NOT NULL REFERENCES agents(id), session_id TEXT,
 label TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL, finished_at TEXT);
CREATE TABLE IF NOT EXISTS request_traces (
 request_id INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
 trace_id TEXT NOT NULL REFERENCES traces(id) ON DELETE CASCADE,
 PRIMARY KEY(request_id,trace_id));
CREATE TABLE IF NOT EXISTS trace_events (
 id INTEGER PRIMARY KEY, trace_id TEXT NOT NULL REFERENCES traces(id) ON DELETE CASCADE,
 kind TEXT NOT NULL, name TEXT NOT NULL, status TEXT NOT NULL,
 request_id INTEGER REFERENCES requests(id) ON DELETE CASCADE, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS model_usage (
 event_key TEXT PRIMARY KEY, agent_id TEXT NOT NULL REFERENCES agents(id),
 team_id TEXT REFERENCES teams(id), trace_id TEXT REFERENCES traces(id) ON DELETE CASCADE,
 model TEXT NOT NULL, input_tokens INTEGER NOT NULL, output_tokens INTEGER NOT NULL,
 usage_known INTEGER NOT NULL, estimated_cost REAL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS notifications (
 id INTEGER PRIMARY KEY, event_key TEXT NOT NULL UNIQUE,
 request_id INTEGER REFERENCES requests(id) ON DELETE CASCADE,
 agent_id TEXT REFERENCES agents(id), message TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'queued', attempts INTEGER NOT NULL DEFAULT 0,
 error_type TEXT, created_at TEXT NOT NULL, sent_at TEXT);
CREATE TRIGGER IF NOT EXISTS notify_new_request AFTER INSERT ON requests
 WHEN NEW.status IN ('pending_approval','denied') BEGIN
 INSERT OR IGNORE INTO notifications(event_key,request_id,agent_id,message,created_at)
 VALUES ('request:'||NEW.id||':'||NEW.status,NEW.id,NEW.agent_id,
 'Request '||NEW.id||' for agent '||NEW.agent_id||': '||NEW.status||' ($'||NEW.amount||' at '||NEW.merchant||')',NEW.created_at);
END;
CREATE TRIGGER IF NOT EXISTS track_request_status AFTER UPDATE OF status ON requests
 WHEN NEW.status != OLD.status BEGIN
 INSERT INTO trace_events(trace_id,kind,name,status,request_id,created_at)
 SELECT trace_id,'request',NEW.merchant,NEW.status,NEW.id,strftime('%Y-%m-%dT%H:%M:%SZ','now')
 FROM request_traces WHERE request_id=NEW.id;
 INSERT OR IGNORE INTO notifications(event_key,request_id,agent_id,message,created_at)
 SELECT 'request:'||NEW.id||':'||NEW.status,NEW.id,NEW.agent_id,
 'Request '||NEW.id||' for agent '||NEW.agent_id||': '||NEW.status||' ($'||NEW.amount||' at '||NEW.merchant||')',
 strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE NEW.status != 'executing';
END;
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
