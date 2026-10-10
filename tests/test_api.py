from concurrent.futures import ThreadPoolExecutor
import hashlib
from threading import Event

from fastapi.testclient import TestClient
import pytest

from gateway import db, main
from gateway.models import RECORD_FIELDS

ADMIN = {"X-Admin-Key": "test-admin"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "api.db"))
    monkeypatch.setenv("ADMIN_KEY", "test-admin")
    monkeypatch.setenv("APPROVAL_TTL_SECONDS", "300")
    monkeypatch.setattr(db, "TOKEN_PATH", tmp_path / ".demo_token")
    monkeypatch.setattr(main, "_execute", lambda req: {"ok": True, "receipt_id": f"test_{req['id']}", "detail": "mock"})
    monkeypatch.setattr(main, "_explain", lambda *args: "Test explanation")
    with TestClient(main.app) as session:
        session.headers["Authorization"] = "Bearer " + db.TOKEN_PATH.read_text()
        yield session


def spend(client, amount=10, key="one"):
    return client.post("/request", json={"merchant": "openai.com", "amount": amount,
                                       "reason": "test", "idempotency_key": key})


def test_allow_and_replay(client, monkeypatch):
    calls = []
    def execute(req):
        calls.append(req)
        return {"ok": True, "receipt_id": "receipt", "detail": "mock"}
    monkeypatch.setattr(main, "_execute", execute)
    first = spend(client).json()
    assert first["decision"] == "allow" and first["status"] == "settled"
    assert set(first) == {"request_id", "decision", "status", "reason", "receipt_id"}
    assert spend(client).json() == first
    assert len(calls) == 1
    row = client.get(f"/requests/{first['request_id']}").json()
    assert set(row) == set(RECORD_FIELDS)
    feed = client.get("/feed", headers=ADMIN).json()
    assert feed["agents"][0]["spent"] == 10
    assert "token_hash" not in str(feed)


@pytest.mark.parametrize("approve,status,spent", [(True, "settled", 40), (False, "rejected", 0)])
def test_hold_decision(client, approve, status, spent):
    result = spend(client, 40).json()
    assert result["decision"] == "hold"
    pending = client.get("/pending", headers=ADMIN).json()["requests"]
    assert pending[0]["explanation"] == "Test explanation"
    response = client.post(f"/approvals/{result['request_id']}", headers=ADMIN,
                           json={"approve": approve, "approver": "reviewer"})
    assert response.json()["status"] == status
    assert response.json()["approver"] == "reviewer"
    assert client.post(f"/approvals/{result['request_id']}", headers=ADMIN,
                       json={"approve": True, "approver": "reviewer"}).status_code == 409
    agent = client.get("/feed", headers=ADMIN).json()["agents"][0]
    assert agent["spent"] == spent and agent["reserved"] == 0


def test_expiry_committed_on_conflict(client):
    result = spend(client, 40).json()
    with db.transaction() as conn:
        conn.execute("UPDATE requests SET expires_at='2000-01-01T00:00:00Z'")
    response = client.post(f"/approvals/{result['request_id']}", headers=ADMIN,
                           json={"approve": True, "approver": "reviewer"})
    assert response.status_code == 409
    with db.connection() as conn:
        assert conn.execute("SELECT status FROM requests").fetchone()[0] == "expired"
    assert client.get("/pending", headers=ADMIN).json() == {"requests": []}


@pytest.mark.parametrize("endpoint", ["/pending", "/feed", "/requests/{id}"])
def test_read_expires_pending(client, endpoint):
    result = spend(client, 40).json()
    with db.transaction() as conn:
        conn.execute("UPDATE requests SET expires_at='2000-01-01T00:00:00Z'")
    assert client.get(endpoint.format(id=result["request_id"]), headers=ADMIN).status_code == 200
    with db.connection() as conn:
        assert conn.execute("SELECT status FROM requests").fetchone()[0] == "expired"


def test_budget_denial(client):
    assert spend(client, 40).json()["decision"] == "hold"
    result = spend(client, 20, "over-budget").json()
    assert result["status"] == "denied"
    assert result["reason"] == "exceeds remaining budget"


@pytest.mark.parametrize("scope", [{"scope": "global"}, {"scope": "agent", "agent_id": "research-bot"}])
def test_kill_resume(client, scope):
    result = spend(client, 40).json()
    assert client.post("/kill", headers=ADMIN, json=scope).json() == {"ok": True}
    assert client.get(f"/requests/{result['request_id']}").json()["status"] == "cancelled"
    assert spend(client, key="killed").json()["decision"] == "deny"
    assert client.post("/resume", headers=ADMIN, json=scope).json() == {"ok": True}
    assert spend(client, key="resumed").json()["status"] == "settled"


def test_auth_and_unknown(client):
    assert client.post("/request", headers={"Authorization": "Bearer wrong"}, json={}).status_code == 401
    assert client.get("/feed").status_code == 403
    assert client.get("/feed", headers={"X-Admin-Key": "wrong"}).status_code == 403
    assert client.get("/requests/999").status_code == 404
    assert client.post("/approvals/999", headers=ADMIN, json={"approve": True, "approver": "a"}).status_code == 404
    assert client.get("/health").json() == {"ok": True}
    client.headers.pop("Authorization")
    assert client.post("/request", json={}).status_code == 401


@pytest.mark.parametrize("body", [{}, [], None, {"merchant": "openai.com", "amount": True, "reason": "x", "idempotency_key": "x"}])
def test_invalid_body(client, body):
    response = client.post("/request", json=body)
    assert response.status_code == 200
    assert response.json()["decision"] == "deny"


def test_invalid_json(client):
    response = client.post("/request", content="{", headers={"Content-Type": "application/json"})
    assert response.status_code == 200 and response.json()["status"] == "denied"


def test_unexpected_exception(client, monkeypatch):
    def broken(*args):
        raise RuntimeError("private diagnostic")
    monkeypatch.setattr(main.budget, "reserve", broken)
    response = spend(client)
    assert response.status_code == 200 and response.json()["decision"] == "deny"
    assert "private diagnostic" not in response.text


@pytest.mark.parametrize("raises", [True, False])
def test_executor_failure(client, monkeypatch, raises):
    def broken(req):
        if raises:
            raise RuntimeError("failure")
        return {"ok": False, "receipt_id": None, "detail": "failure"}
    monkeypatch.setattr(main, "_execute", broken)
    assert spend(client).json()["status"] == "failed"
    assert client.get("/feed", headers=ADMIN).json()["agents"][0]["available"] == 50


def test_explainer_failure(client, monkeypatch):
    def broken(*args):
        raise RuntimeError("failure")
    monkeypatch.setattr(main, "_explain", broken)
    assert spend(client, 40).json()["status"] == "pending_approval"


def test_reset_preserves_token(client):
    spend(client)
    token = db.TOKEN_PATH.read_text()
    assert client.post("/reset", headers=ADMIN).json() == {"ok": True}
    assert db.TOKEN_PATH.read_text() == token
    assert client.get("/feed", headers=ADMIN).json()["requests"] == []
    assert spend(client).json()["status"] == "settled"


def test_cross_agent_ownership(client):
    original = spend(client).json()
    with db.transaction() as conn:
        conn.execute("INSERT INTO agents VALUES ('other','Other',?,'active')", (hashlib.sha256(b"other-token").hexdigest(),))
    client.headers["Authorization"] = "Bearer other-token"
    assert client.get(f"/requests/{original['request_id']}").status_code == 404
    assert spend(client).json()["decision"] == "deny"


def test_inflight_replay_never_executes_twice(client, monkeypatch):
    started, finish = Event(), Event()
    calls = []
    def execute(req):
        calls.append(req)
        started.set()
        assert finish.wait(5)
        return {"ok": True, "receipt_id": "once", "detail": "mock"}
    monkeypatch.setattr(main, "_execute", execute)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(spend, client)
        try:
            assert started.wait(5)
            assert spend(client).json()["status"] == "executing"
            assert client.post("/reset", headers=ADMIN).status_code == 409
        finally:
            finish.set()
        assert first.result().json()["status"] == "settled"
    assert len(calls) == 1
