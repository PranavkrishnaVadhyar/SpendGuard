"""Atomic policy check and reservation using a derived UTC daily ledger."""

from datetime import datetime, timedelta
from decimal import Decimal
import json
from uuid import uuid4

from spendguard import db, policy, teams
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
    usage = conn.execute("""SELECT estimated_cost FROM model_usage
        WHERE agent_id=? AND substr(created_at,1,10)=?""", (agent_id, timestamp[:10])).fetchall()
    model_cost = sum((Decimal(str(r[0])) for r in usage if r[0] is not None), Decimal(0))
    return {"daily_budget": float(daily), "spent": float(spent),
            "reserved": float(reserved), "model_estimated_cost": float(model_cost),
            "unpriced_calls": sum(r[0] is None for r in usage),
            "available": float(daily - spent - reserved - model_cost)}


def reserve(db_path, agent_id: str, merchant: str, amount: float, reason: str = "",
            idempotency_key: str | None = None, approval_ttl_seconds=300,
            tool_call=None) -> tuple[dict, bool]:
    key = str(uuid4()) if idempotency_key is None else idempotency_key
    with db.transaction(db_path) as conn:
        existing = conn.execute("SELECT * FROM requests WHERE idempotency_key=?", (key,)).fetchone()
        if existing:
            if existing["agent_id"] != agent_id:
                raise ValueError("idempotency key belongs to another agent")
            saved = conn.execute("SELECT * FROM tool_calls WHERE request_id=?", (existing["id"],)).fetchone()
            if tool_call is not None:
                if (saved is None or saved["tool_name"] != tool_call["name"]
                        or saved["arguments"] != tool_call["arguments"]
                        or existing["merchant"] != policy.normalize_merchant(merchant)
                        or existing["amount"] != amount):
                    raise ValueError("idempotency key belongs to a different tool call")
            elif saved is not None:
                raise ValueError("idempotency key belongs to a tool call")
            if tool_call is not None:
                from spendguard.insights import link_request
                link_request(conn, tool_call.get("trace_id"), existing["id"], agent_id, existing["status"])
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
        member = conn.execute("SELECT team_id FROM team_members WHERE agent_id=?", (agent_id,)).fetchone()
        if member is not None and decision.decision in {"allow", "hold"}:
            shared = teams.ledger(conn, member[0], timestamp)
            if amount > shared["available"]:
                decision = policy.Decision("deny", "team budget exceeded")
        status = {"allow": "allowed", "hold": "pending_approval", "deny": "denied"}[decision.decision]
        expires = None
        if status == "pending_approval":
            expires = (datetime.fromisoformat(timestamp.replace("Z", "+00:00")) + timedelta(seconds=approval_ttl_seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")
        cursor = conn.execute("""INSERT INTO requests
            (idempotency_key,agent_id,merchant,amount,reason,status,decision_reason,created_at,decided_at,expires_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)""", (key, agent_id,
            policy.normalize_merchant(merchant), amount, reason, status,
            decision.reason, timestamp, timestamp if status == "denied" else None, expires))
        if tool_call is not None:
            conn.execute("INSERT INTO tool_calls (request_id,tool_name,arguments) VALUES (?,?,?)",
                         (cursor.lastrowid, tool_call["name"], tool_call["arguments"]))
            from spendguard.insights import link_request
            link_request(conn, tool_call.get("trace_id"), cursor.lastrowid, agent_id, status)
        if member is not None:
            conn.execute("INSERT INTO request_teams VALUES (?,?)", (cursor.lastrowid, member[0]))
        return dict(conn.execute("SELECT * FROM requests WHERE id=?", (cursor.lastrowid,)).fetchone()), True
