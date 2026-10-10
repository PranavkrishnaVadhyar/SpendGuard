"""SpendGuard public API, adapted from the gateway lifecycle implementation."""

import json
import math
from pathlib import Path
from threading import Thread
import time

from spendguard import budget, db
from spendguard.constants import TERMINAL
from spendguard.errors import InvalidState, NotFound, UnknownAgent
from spendguard.models import Outcome, Policy, RequestRecord
from spendguard.policy import normalize_merchant

try:
    from spendguard.adapters import execute as _default_execute
except Exception:
    def _default_execute(req):
        return {"ok": True, "receipt_id": f"rcpt_local_{req['id']}", "detail": "local fallback"}

try:
    from spendguard.explain import explain as _default_explain
except Exception:
    def _default_explain(req, spent_today, daily_budget):
        return f"Agent requests ${req['amount']:.2f} from {req['merchant']}. Reason given: {req.get('reason') or 'none'}."


def _text(value, label, limit=200):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"invalid {label}")


def _number(value):
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def _validated_policy(policy):
    if not isinstance(policy, Policy):
        raise ValueError("policy must be a Policy")
    values = (policy.daily_budget, policy.per_txn_cap, policy.approval_threshold)
    if any(not _number(value) or value < 0 for value in values):
        raise ValueError("policy limits must be finite non-negative numbers")
    if not isinstance(policy.allowlist, list) or any(
        not isinstance(item, str) or not normalize_merchant(item) for item in policy.allowlist
    ):
        raise ValueError("allowlist must contain valid merchant hostnames")
    return (*values, json.dumps([normalize_merchant(item) for item in policy.allowlist]))


def _fetch(conn, request_id):
    row = conn.execute("SELECT * FROM requests WHERE id=?", (request_id,)).fetchone()
    if row is None:
        raise NotFound("unknown request")
    return dict(row)


def _outcome(row):
    status = row["status"]
    decision = "hold" if status == "pending_approval" else "allow" if status in {
        "allowed", "approved", "executing", "settled"
    } else "deny"
    return Outcome(decision, status, row["decision_reason"] or "", row["id"],
                   row["receipt_id"], RequestRecord.from_dict(row))


class SpendGuard:
    def __init__(self, db_path="spendguard.db", approval_ttl_seconds=300,
                 executor=None, explainer=None, on_hold=None):
        if not _number(approval_ttl_seconds) or approval_ttl_seconds < 0:
            raise ValueError("approval_ttl_seconds must be finite and non-negative")
        if not str(db_path) or str(db_path) == ":memory:":
            raise ValueError("db_path must name a SQLite file")
        for callback in (executor, explainer, on_hold):
            if callback is not None and not callable(callback):
                raise ValueError("callbacks must be callable")
        self.db_path = str(Path(db_path).resolve())
        self.approval_ttl_seconds = approval_ttl_seconds
        self.executor = _default_execute if executor is None else executor
        self.explainer = _default_explain if explainer is None else explainer
        self.on_hold = on_hold
        db.initialize(self.db_path)

    def create_agent(self, agent_id: str, policy: Policy, name: str | None = None) -> None:
        _text(agent_id, "agent id")
        if name is not None:
            _text(name, "agent name")
        values = _validated_policy(policy)
        with db.transaction(self.db_path) as conn:
            conn.execute("""INSERT INTO agents (id,name,status) VALUES (?,?,'active')
                ON CONFLICT(id) DO UPDATE SET name=excluded.name""", (agent_id, name or agent_id))
            conn.execute("""INSERT INTO policies VALUES (?,?,?,?,?) ON CONFLICT(agent_id)
                DO UPDATE SET daily_budget=excluded.daily_budget, per_txn_cap=excluded.per_txn_cap,
                approval_threshold=excluded.approval_threshold, allowlist=excluded.allowlist""",
                         (agent_id, *values))

    def update_policy(self, agent_id: str, policy: Policy) -> None:
        values = _validated_policy(policy)
        with db.transaction(self.db_path) as conn:
            if not conn.execute("SELECT 1 FROM agents WHERE id=?", (agent_id,)).fetchone():
                raise UnknownAgent("unknown agent")
            conn.execute("""UPDATE policies SET daily_budget=?,per_txn_cap=?,approval_threshold=?,
                allowlist=? WHERE agent_id=?""", (*values, agent_id))

    def request(self, agent_id: str, merchant: str, amount: float, reason: str = "",
                idempotency_key: str | None = None) -> Outcome:
        return self._request(agent_id, merchant, amount, reason, idempotency_key)

    def _request(self, agent_id, merchant, amount, reason="", idempotency_key=None,
                 tool_call=None, tool_executor=None):
        try:
            _text(agent_id, "agent id")
            _text(merchant, "merchant", 2048)
            if not _number(amount):
                return Outcome("deny", "denied", "invalid amount", None, None, None)
            if not isinstance(reason, str) or len(reason) > 4000:
                raise ValueError("invalid reason")
            if idempotency_key is not None:
                _text(idempotency_key, "idempotency key")
            row, created = budget.reserve(self.db_path, agent_id, merchant, float(amount), reason,
                                          idempotency_key, self.approval_ttl_seconds, tool_call)
            if created and row["status"] == "allowed":
                row = self._execute_request(row["id"], tool_executor)
            elif created and row["status"] == "pending_approval":
                self._start_hold_tasks(row)
            return _outcome(row)
        except UnknownAgent:
            return Outcome("deny", "denied", "unknown agent", None, None, None)
        except Exception:
            return Outcome("deny", "denied", "request could not be processed", None, None, None)

    def _execute_request(self, request_id, tool_executor=None):
        # Claim once under the write lock. Never execute an idempotent replay.
        with db.transaction(self.db_path) as conn:
            row = _fetch(conn, request_id)
            if row["status"] not in {"allowed", "approved"}:
                return row
            tool_call = conn.execute("SELECT * FROM tool_calls WHERE request_id=?", (request_id,)).fetchone()
            # Approval UIs authorize tools; only their owning wrapper executes them.
            if tool_call is not None and tool_executor is None:
                return row
            agent = conn.execute("SELECT status FROM agents WHERE id=?", (row["agent_id"],)).fetchone()
            if db.killed(conn) or agent["status"] != "active":
                conn.execute("""UPDATE requests SET status='cancelled', decided_at=?,
                    decision_reason='kill switch active' WHERE id=?""", (db.now(), request_id))
                return _fetch(conn, request_id)
            conn.execute("UPDATE requests SET status='executing' WHERE id=?", (request_id,))
        try:
            tool_result = None
            if tool_call is not None:
                value = tool_executor(json.loads(tool_call["arguments"]))
                try:
                    tool_result = json.dumps(value, default=str, ensure_ascii=False, allow_nan=False)
                except (TypeError, ValueError):
                    tool_result = json.dumps(str(value))
                result = {"ok": True, "receipt_id": f"tool_{request_id}"}
            else:
                result = self.executor({key: row[key] for key in (
                    "id", "agent_id", "merchant", "amount", "reason", "idempotency_key")})
            success = result.get("ok") is True
            receipt = result.get("receipt_id")
            if receipt is not None and not isinstance(receipt, str):
                success = False
        except Exception:
            success, receipt = False, None
        with db.transaction(self.db_path) as conn:
            status = "settled" if success else "failed"
            decision_reason = row["decision_reason"] if success else "execution failed"
            conn.execute("""UPDATE requests SET status=?,receipt_id=?,decided_at=?,decision_reason=?
                WHERE id=? AND status='executing'""",
                         (status, receipt if success else None, db.now(), decision_reason, request_id))
            if tool_call is not None and success:
                conn.execute("UPDATE tool_calls SET result=? WHERE request_id=?", (tool_result, request_id))
            return _fetch(conn, request_id)

    def _start_hold_tasks(self, row):
        def notify():
            if self.on_hold is not None:
                self.on_hold(RequestRecord.from_dict(row))

        def explain():
            with db.connection(self.db_path) as conn:
                balances = budget.ledger(conn, row["agent_id"], db.now())
            explanation = self.explainer(dict(row), balances["spent"], balances["daily_budget"])
            if isinstance(explanation, str):
                with db.transaction(self.db_path) as conn:
                    conn.execute("""UPDATE requests SET explanation=?
                        WHERE id=? AND idempotency_key=? AND status='pending_approval'""",
                                 (explanation, row["id"], row["idempotency_key"]))

        def safely(callback):
            try:
                callback()
            except Exception:
                pass

        # Independent workers ensure a slow notification cannot delay explanation.
        for callback in (notify, explain):
            try:
                Thread(target=safely, args=(callback,), daemon=True).start()
            except Exception:
                pass

    def wait(self, request_id: int, timeout: float = 300, interval: float = 0.5) -> RequestRecord:
        if not _number(timeout) or timeout < 0 or not _number(interval) or interval <= 0:
            raise ValueError("timeout must be non-negative and interval positive")
        deadline = time.monotonic() + timeout
        while True:
            record = self.get(request_id)
            remaining = deadline - time.monotonic()
            if record.status in TERMINAL or remaining <= 0:
                return record
            time.sleep(min(interval, remaining))

    def get(self, request_id: int) -> RequestRecord:
        with db.transaction(self.db_path) as conn:
            db.expire(conn, db.now())
            row = conn.execute("SELECT * FROM requests WHERE id=?", (request_id,)).fetchone()
        if row is None:
            raise NotFound("unknown request")
        return RequestRecord.from_dict(row)

    def pending(self) -> list[RequestRecord]:
        with db.transaction(self.db_path) as conn:
            db.expire(conn, db.now())
            rows = conn.execute("SELECT * FROM requests WHERE status='pending_approval' ORDER BY id").fetchall()
            return [RequestRecord.from_dict(row) for row in rows]

    def feed(self, limit: int = 50) -> list[RequestRecord]:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
            raise ValueError("limit must be a non-negative integer")
        with db.transaction(self.db_path) as conn:
            db.expire(conn, db.now())
            rows = conn.execute("SELECT * FROM requests ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            return [RequestRecord.from_dict(row) for row in rows]

    def approve(self, request_id: int, approver: str = "admin") -> RequestRecord:
        return self._decide(request_id, approver, True)

    def reject(self, request_id: int, approver: str = "admin") -> RequestRecord:
        return self._decide(request_id, approver, False)

    def _decide(self, request_id, approver, approve):
        _text(approver, "approver")
        error = None
        with db.transaction(self.db_path) as conn:
            timestamp = db.now()
            db.expire(conn, timestamp)
            existing = conn.execute("SELECT * FROM requests WHERE id=?", (request_id,)).fetchone()
            if existing is None:
                error = NotFound("unknown request")
            elif existing["status"] != "pending_approval":
                error = InvalidState("request is not pending approval")
            else:
                agent = conn.execute("SELECT status FROM agents WHERE id=?", (existing["agent_id"],)).fetchone()
                status = "rejected"
                reason = "rejected by approver"
                if approve:
                    status, reason = "approved", "approved by approver"
                    if db.killed(conn) or agent["status"] != "active":
                        status, reason = "cancelled", "kill switch active"
                        error = InvalidState("request cancelled by kill switch")
                conn.execute("""UPDATE requests SET status=?,approver=?,decided_at=?,decision_reason=?
                    WHERE id=?""", (status, approver, timestamp, reason, request_id))
                row = _fetch(conn, request_id)
        # Commit expiry/cancellation before raising the public state error.
        if error is not None:
            raise error
        if approve:
            row = self._execute_request(request_id)
            if row["status"] == "cancelled":
                raise InvalidState("request cancelled by kill switch")
        return RequestRecord.from_dict(row)

    def kill(self, agent_id: str | None = None) -> None:
        self._change_switch(agent_id, True)

    def resume(self, agent_id: str | None = None) -> None:
        self._change_switch(agent_id, False)

    def _change_switch(self, agent_id, kill):
        with db.transaction(self.db_path) as conn:
            if agent_id is None:
                conn.execute("INSERT OR REPLACE INTO settings VALUES ('kill_switch_global', ?)",
                             ("1" if kill else "0",))
            else:
                if not conn.execute("SELECT 1 FROM agents WHERE id=?", (agent_id,)).fetchone():
                    raise UnknownAgent("unknown agent")
                conn.execute("UPDATE agents SET status=? WHERE id=?", ("killed" if kill else "active", agent_id))
            if kill:
                sql = """UPDATE requests SET status='cancelled',decided_at=?,decision_reason='kill switch active'
                    WHERE status IN ('pending_approval','approved')"""
                params = [db.now()]
                if agent_id is not None:
                    sql += " AND agent_id=?"
                    params.append(agent_id)
                conn.execute(sql, params)

    def status(self) -> dict:
        with db.transaction(self.db_path) as conn:
            timestamp = db.now()
            db.expire(conn, timestamp)
            agents = [{**dict(row), **budget.ledger(conn, row["id"], timestamp)}
                      for row in conn.execute("SELECT id,name,status FROM agents ORDER BY id").fetchall()]
            return {"kill_global": db.killed(conn), "agents": agents}

    def reset(self) -> None:
        with db.transaction(self.db_path) as conn:
            if conn.execute("SELECT 1 FROM requests WHERE status='executing' LIMIT 1").fetchone():
                raise InvalidState("execution in progress")
            conn.execute("DELETE FROM requests")
            conn.execute("UPDATE agents SET status='active'")
            conn.execute("INSERT OR REPLACE INTO settings VALUES ('kill_switch_global', '0')")
