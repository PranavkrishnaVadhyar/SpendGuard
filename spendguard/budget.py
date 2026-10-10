"""Atomic policy check and reservation using a derived UTC daily ledger."""

from datetime import datetime, timedelta
from decimal import Decimal
import json
from uuid import uuid4

from spendguard import db, policy
from spendguard.constants import RESERVING
from spendguard.errors import UnknownAgent


def ledger(conn, agent_id: str, timestamp: str) -> dict:
    policy_row = conn.execute("SELECT daily_budget FROM policies WHERE agent_id=?", (agent_id,)).fetchone()
    if policy_row is None:
        raise UnknownAgent("unknown agent")
    rows = conn.execute("SELECT amount, status FROM requests WHERE agent_id=? AND substr(created_at,1,10)=?",
                        (agent_id, timestamp[:10])).fetchall()
    # Decimal summation avoids admitting overspend through binary-float addition.
    spent = sum((Decimal(str(r["amount"])) for r in rows if r["status"] == "settled"), Decimal(0))
    reserved = sum((Decimal(str(r["amount"])) for r in rows if r["status"] in RESERVING), Decimal(0))
    daily = Decimal(str(policy_row["daily_budget"]))
    return {"daily_budget": float(daily), "spent": float(spent),
            "reserved": float(reserved), "available": float(daily - spent - reserved)}


def reserve(db_path, agent_id: str, merchant: str, amount: float, reason: str = "",
            idempotency_key: str | None = None, approval_ttl_seconds=300) -> tuple[dict, bool]:
    key = str(uuid4()) if idempotency_key is None else idempotency_key
    with db.transaction(db_path) as conn:
        existing = conn.execute("SELECT * FROM requests WHERE idempotency_key=?", (key,)).fetchone()
        if existing:
            if existing["agent_id"] != agent_id:
                raise ValueError("idempotency key belongs to another agent")
            return dict(existing), False
        timestamp = db.now()
        db.expire(conn, timestamp)
        agent = conn.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
        if agent is None:
            raise UnknownAgent("unknown agent")
        rules = conn.execute("SELECT * FROM policies WHERE agent_id=?", (agent_id,)).fetchone()
        balances = ledger(conn, agent_id, timestamp)
        decision = policy.evaluate(global_kill=db.killed(conn), agent_status=agent["status"],
            amount=amount, merchant=merchant, allowlist=json.loads(rules["allowlist"]),
            per_txn_cap=rules["per_txn_cap"], available=balances["available"],
            approval_threshold=rules["approval_threshold"])
        status = {"allow": "allowed", "hold": "pending_approval", "deny": "denied"}[decision.decision]
        expires = None
        if status == "pending_approval":
            expires = (datetime.fromisoformat(timestamp.replace("Z", "+00:00")) + timedelta(seconds=approval_ttl_seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")
        cursor = conn.execute("""INSERT INTO requests
            (idempotency_key,agent_id,merchant,amount,reason,status,decision_reason,created_at,decided_at,expires_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)""", (key, agent_id,
            policy.normalize_merchant(merchant), amount, reason, status,
            decision.reason, timestamp, timestamp if status == "denied" else None, expires))
        return dict(conn.execute("SELECT * FROM requests WHERE id=?", (cursor.lastrowid,)).fetchone()), True
