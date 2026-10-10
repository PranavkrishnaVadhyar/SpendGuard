"""SpendGuard HTTP contract and request lifecycle."""

from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from gateway import auth, budget, db
from gateway.models import Approval, SpendRequest, Switch, record

load_dotenv(db.ROOT / ".env")

try:
    from gateway.executor import execute as _execute
except Exception:
    def _execute(req):
        return {"ok": True, "receipt_id": f"rcpt_local_{req['id']}", "detail": "local fallback"}

try:
    from gateway.explainer import explain as _explain
except Exception:
    def _explain(req, spent_today, daily_budget):
        return f"Agent requests ${req['amount']:.2f} from {req['merchant']}. Reason given: {req.get('reason') or 'none'}."


@asynccontextmanager
async def lifespan(app):
    db.initialize()
    yield


app = FastAPI(title="SpendGuard", lifespan=lifespan)


def denial(reason="request could not be processed"):
    return {"request_id": None, "decision": "deny", "status": "denied", "reason": reason, "receipt_id": None}


@app.middleware("http")
async def fail_closed(request: Request, call_next):
    if request.method != "POST" or request.url.path != "/request":
        return await call_next(request)
    try:
        response = await call_next(request)
        if response.status_code >= 500:
            return JSONResponse(denial())
        return response
    except Exception:
        return JSONResponse(denial())


def fetch(conn, request_id):
    row = conn.execute("SELECT * FROM requests WHERE id=?", (request_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "unknown request")
    return dict(row)


def execute_request(request_id):
    # Claim once under the write lock. Never execute an idempotent replay.
    with db.transaction() as conn:
        row = fetch(conn, request_id)
        if row["status"] not in {"allowed", "approved"}:
            return row
        agent = conn.execute("SELECT status FROM agents WHERE id=?", (row["agent_id"],)).fetchone()
        if db.killed(conn) or agent["status"] != "active":
            conn.execute("UPDATE requests SET status='cancelled', decided_at=?, decision_reason='kill switch active' WHERE id=?",
                         (db.now(), request_id))
            return fetch(conn, request_id)
        conn.execute("UPDATE requests SET status='executing' WHERE id=?", (request_id,))
    try:
        result = _execute({key: row[key] for key in ("id", "agent_id", "merchant", "amount", "reason", "idempotency_key")})
        success = result.get("ok") is True
        receipt = result.get("receipt_id")
        if receipt is not None and not isinstance(receipt, str):
            success = False
    except Exception:
        success, receipt = False, None
    with db.transaction() as conn:
        conn.execute("UPDATE requests SET status=?, receipt_id=?, decided_at=? WHERE id=? AND status='executing'",
                     ("settled" if success else "failed", receipt if success else None, db.now(), request_id))
        return fetch(conn, request_id)


def submit(agent_id, body):
    row, created = budget.reserve(agent_id, body)
    if created and row["status"] == "allowed":
        row = execute_request(row["id"])
    elif created and row["status"] == "pending_approval":
        try:
            with db.connection() as conn:
                balances = budget.ledger(conn, agent_id, db.now())
            explanation = _explain(row, balances["spent"], balances["daily_budget"])
            if isinstance(explanation, str):
                with db.transaction() as conn:
                    conn.execute("UPDATE requests SET explanation=? WHERE id=? AND status='pending_approval'", (explanation, row["id"]))
        except Exception:
            pass
        with db.connection() as conn:
            row = fetch(conn, row["id"])
    status = row["status"]
    decision = "hold" if status == "pending_approval" else "allow" if status in {"allowed", "approved", "executing", "settled"} else "deny"
    return {"request_id": row["id"], "decision": decision, "status": status,
            "reason": "execution failed" if status == "failed" else row["decision_reason"], "receipt_id": row["receipt_id"]}


@app.post("/request")
async def request_spend(request: Request, agent_id: str = Depends(auth.agent_id)):
    try:
        body = SpendRequest.model_validate(await request.json())
    except Exception:
        return denial("invalid request body")
    try:
        return await run_in_threadpool(submit, agent_id, body)
    except Exception:
        return denial()


@app.get("/requests/{request_id}")
def get_request(request_id: int, agent_id: str = Depends(auth.agent_id)):
    with db.transaction() as conn:
        db.expire(conn, db.now())
        row = fetch(conn, request_id)
        if row["agent_id"] != agent_id:
            raise HTTPException(404, "unknown request")
        return record(row)


@app.get("/feed", dependencies=[Depends(auth.admin)])
def feed(limit: int = Query(default=50, ge=1, le=1000)):
    with db.transaction() as conn:
        timestamp = db.now()
        db.expire(conn, timestamp)
        agents = [{**dict(row), **budget.ledger(conn, row["id"], timestamp)}
                  for row in conn.execute("SELECT id,name,status FROM agents ORDER BY id").fetchall()]
        rows = conn.execute("SELECT * FROM requests ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return {"kill_global": db.killed(conn), "agents": agents, "requests": [record(r) for r in rows]}


@app.get("/pending", dependencies=[Depends(auth.admin)])
def pending():
    with db.transaction() as conn:
        db.expire(conn, db.now())
        rows = conn.execute("SELECT * FROM requests WHERE status='pending_approval' ORDER BY id DESC").fetchall()
        return {"requests": [record(row) for row in rows]}


@app.post("/approvals/{request_id}", dependencies=[Depends(auth.admin)])
def approve(request_id: int, body: Approval):
    invalid = False
    with db.transaction() as conn:
        timestamp = db.now()
        db.expire(conn, timestamp)
        row = fetch(conn, request_id)
        if row["status"] != "pending_approval":
            invalid = True
        else:
            agent = conn.execute("SELECT status FROM agents WHERE id=?", (row["agent_id"],)).fetchone()
            status = "rejected"
            if body.approve:
                status = "cancelled" if db.killed(conn) or agent["status"] != "active" else "approved"
            conn.execute("UPDATE requests SET status=?, approver=?, decided_at=? WHERE id=?",
                         (status, body.approver, timestamp, request_id))
            row = fetch(conn, request_id)
    # Raise after commit so lazy expiry persists even for an invalid approval.
    if invalid:
        raise HTTPException(409, "request is not pending approval")
    if row["status"] == "approved":
        row = execute_request(request_id)
    return record(row)


def change_switch(body: Switch, kill: bool):
    with db.transaction() as conn:
        if body.scope == "global":
            conn.execute("INSERT OR REPLACE INTO settings VALUES ('kill_switch_global', ?)", ("1" if kill else "0",))
        else:
            if not conn.execute("SELECT 1 FROM agents WHERE id=?", (body.agent_id,)).fetchone():
                raise HTTPException(404, "unknown agent")
            conn.execute("UPDATE agents SET status=? WHERE id=?", ("killed" if kill else "active", body.agent_id))
        if kill:
            sql = "UPDATE requests SET status='cancelled', decided_at=?, decision_reason='kill switch active' WHERE status IN ('pending_approval','approved')"
            params = [db.now()]
            if body.scope == "agent":
                sql += " AND agent_id=?"
                params.append(body.agent_id)
            conn.execute(sql, params)
    return {"ok": True}


@app.post("/kill", dependencies=[Depends(auth.admin)])
def kill(body: Switch):
    return change_switch(body, True)


@app.post("/resume", dependencies=[Depends(auth.admin)])
def resume(body: Switch):
    return change_switch(body, False)


@app.post("/reset", dependencies=[Depends(auth.admin)])
def reset():
    with db.transaction() as conn:
        if conn.execute("SELECT 1 FROM requests WHERE status='executing' LIMIT 1").fetchone():
            raise HTTPException(409, "execution in progress")
        conn.execute("DELETE FROM requests")
        conn.execute("DELETE FROM policies")
        conn.execute("DELETE FROM agents")
        db.seed(conn)
    return {"ok": True}


@app.get("/health")
def health():
    return {"ok": True}
