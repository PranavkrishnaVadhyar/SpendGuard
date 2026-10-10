from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import multiprocessing
from threading import Event, current_thread
import time

import pytest

from spendguard import (
    InvalidState, NotFound, Outcome, Policy, RequestDenied, RequestRecord,
    SpendGuard, SpendGuardError, UnknownAgent, __version__,
)
from spendguard import budget, db


@pytest.fixture
def guard(tmp_path):
    guard = SpendGuard(tmp_path / "guard.db", explainer=lambda *args: None)
    guard.create_agent("research-bot", Policy(50, 100, 25, ["openai.com"]), "Research Bot")
    return guard


def spend(guard, amount=10, key=None):
    return guard.request("research-bot", "openai.com", amount, "test", key)


def test_public_models_and_errors(guard):
    outcome = spend(guard)
    assert isinstance(outcome, Outcome) and outcome.settled
    assert RequestRecord.from_dict(outcome.record.to_dict()) == outcome.record
    assert outcome.record.to_dict() == asdict(outcome.record)
    assert RequestDenied(outcome).outcome is outcome
    assert issubclass(UnknownAgent, SpendGuardError)
    assert __version__ == "0.1.0"


def test_allow_and_replay(guard):
    calls = []
    def execute(req):
        calls.append(req)
        return {"ok": True, "receipt_id": "receipt", "detail": "mock"}
    guard.executor = execute
    first = spend(guard, key="same")
    assert first.decision == "allow" and first.settled
    assert spend(guard, 40, "same") == first
    assert len(calls) == 1
    assert set(calls[0]) == {"id", "agent_id", "merchant", "amount", "reason", "idempotency_key"}
    assert guard.status()["agents"][0]["spent"] == 10


@pytest.mark.parametrize("approve,status,spent", [(True, "settled", 40), (False, "rejected", 0)])
def test_hold_decision(guard, approve, status, spent):
    result = spend(guard, 40)
    assert result.decision == "hold"
    assert guard.pending()[0].id == result.request_id
    decide = guard.approve if approve else guard.reject
    record = decide(result.request_id, "reviewer")
    assert record.status == status and record.approver == "reviewer"
    with pytest.raises(InvalidState):
        guard.approve(result.request_id)
    agent = guard.status()["agents"][0]
    assert agent["spent"] == spent and agent["reserved"] == 0


@pytest.mark.parametrize("operation", ["get", "pending", "feed", "wait", "approve", "reject"])
def test_expiry(guard, operation):
    guard.approval_ttl_seconds = 0
    result = spend(guard, 40)
    method = getattr(guard, operation)
    if operation in {"approve", "reject"}:
        with pytest.raises(InvalidState):
            method(result.request_id)
    elif operation in {"get", "wait"}:
        assert method(result.request_id).status == "expired"
    else:
        method()
    with db.connection(guard.db_path) as conn:
        assert conn.execute("SELECT status FROM requests").fetchone()[0] == "expired"
    assert guard.status()["agents"][0]["available"] == 50


@pytest.mark.parametrize("agent_id", [None, "research-bot"])
def test_kill_resume(guard, agent_id):
    result = spend(guard, 40)
    guard.kill(agent_id)
    assert guard.get(result.request_id).status == "cancelled"
    assert spend(guard).decision == "deny"
    guard.resume(agent_id)
    assert spend(guard).settled
    assert guard.get(result.request_id).status == "cancelled"


def test_agent_kill_is_scoped(guard):
    guard.create_agent("other", Policy(50, 100, 25, ["openai.com"]))
    first = spend(guard, 40)
    second = guard.request("other", "openai.com", 40)
    guard.kill("research-bot")
    assert guard.get(first.request_id).status == "cancelled"
    assert guard.get(second.request_id).status == "pending_approval"


def test_unknown_agent_and_request(guard):
    result = guard.request("missing", "openai.com", 10)
    assert result.decision == "deny" and result.request_id is None
    for method in (guard.get, guard.approve, guard.reject, guard.wait):
        with pytest.raises(NotFound):
            method(999)
    for method in (guard.kill, guard.resume):
        with pytest.raises(UnknownAgent):
            method("missing")
    with pytest.raises(UnknownAgent):
        guard.update_policy("missing", Policy(50, 100, 25, []))


@pytest.mark.parametrize("amount", [None, "10", True, float("nan"), float("inf"), 0, -1, 10**1000])
def test_invalid_amount_never_raises(guard, amount):
    assert spend(guard, amount).decision == "deny"


def test_invalid_arguments_never_raise(guard):
    assert guard.request(None, "openai.com", 10).decision == "deny"
    assert guard.request("research-bot", None, 10).decision == "deny"
    assert guard.request("research-bot", "openai.com", 10, reason={}).decision == "deny"
    assert spend(guard, key=[]).decision == "deny"


def test_unexpected_error_is_sanitized(guard, monkeypatch):
    def broken(*args):
        raise RuntimeError("private diagnostic")
    monkeypatch.setattr(budget, "reserve", broken)
    result = spend(guard)
    assert result.decision == "deny" and result.request_id is None
    assert "private diagnostic" not in result.reason


@pytest.mark.parametrize("failure", ["raise", "false", "malformed"])
def test_executor_failure(guard, failure):
    def broken(req):
        if failure == "raise":
            raise RuntimeError("failure")
        return None if failure == "malformed" else {"ok": False, "receipt_id": None, "detail": "failure"}
    guard.executor = broken
    result = spend(guard)
    assert result.status == "failed" and not result.settled
    assert result.record.decision_reason == "execution failed"
    assert guard.status()["agents"][0]["available"] == 50


def test_hold_workers_do_not_block(guard):
    notified, explaining, release = Event(), Event(), Event()
    def notify(record):
        assert current_thread().daemon
        assert isinstance(record, RequestRecord)
        notified.set()
        release.wait(5)
        raise RuntimeError("notification failure")
    def explain(*args):
        assert current_thread().daemon
        explaining.set()
        release.wait(5)
        return "Test explanation"
    guard.on_hold, guard.explainer = notify, explain
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(spend, guard, 40)
            result = future.result(timeout=2)
            assert notified.wait(2) and explaining.wait(2)
            assert result.status == "pending_approval"
    finally:
        release.set()
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        record = guard.get(result.request_id)
        if record.explanation:
            break
        time.sleep(0.01)
    assert record.explanation == "Test explanation"


def test_explainer_failure_ignored(guard):
    finished = Event()
    def broken(*args):
        finished.set()
        raise RuntimeError("failure")
    guard.explainer = broken
    result = spend(guard, 40)
    assert finished.wait(2)
    assert guard.get(result.request_id).status == "pending_approval"


def test_reset_preserves_agents_policies(guard):
    guard.update_policy("research-bot", Policy(70, 90, 20, ["openai.com"]))
    spend(guard)
    guard.kill()
    guard.kill("research-bot")
    guard.reset()
    assert guard.feed() == []
    status = guard.status()
    assert status["kill_global"] is False
    assert status["agents"][0]["daily_budget"] == 70
    assert status["agents"][0]["name"] == "Research Bot"
    assert status["agents"][0]["status"] == "active"
    assert spend(guard, 21).decision == "hold"


def test_reopen_and_separate_database(guard, tmp_path):
    first = spend(guard)
    guard.kill()
    other = SpendGuard(guard.db_path)
    assert other.get(first.request_id) == first.record
    assert other.status()["kill_global"] is True
    empty = SpendGuard(tmp_path / "empty.db")
    assert empty.status() == {"kill_global": False, "agents": []}


def test_upsert_does_not_revive_killed_agent(guard):
    guard.kill("research-bot")
    guard.create_agent("research-bot", Policy(80, 100, 25, ["openai.com"]), "Updated")
    agent = guard.status()["agents"][0]
    assert agent["name"] == "Updated" and agent["daily_budget"] == 80
    assert agent["status"] == "killed"


def test_wait_and_ordering(guard):
    guard.update_policy("research-bot", Policy(100, 100, 25, ["openai.com"]))
    first, second = spend(guard, 30), spend(guard, 30)
    assert [r.id for r in guard.pending()] == [first.request_id, second.request_id]
    assert [r.id for r in guard.feed(1)] == [second.request_id]
    assert guard.wait(first.request_id, timeout=0).status == "pending_approval"
    with ThreadPoolExecutor(max_workers=1) as pool:
        waiting = pool.submit(guard.wait, first.request_id, 3, 0.01)
        guard.reject(first.request_id)
        assert waiting.result().status == "rejected"


def test_inflight_replay_never_executes_twice(guard):
    started, finish = Event(), Event()
    calls = []
    def execute(req):
        calls.append(req)
        started.set()
        assert finish.wait(5)
        return {"ok": True, "receipt_id": "once", "detail": "mock"}
    guard.executor = execute
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(spend, guard, 10, "same")
        try:
            assert started.wait(2)
            assert spend(guard, key="same").status == "executing"
            with pytest.raises(InvalidState):
                guard.reset()
        finally:
            finish.set()
        assert first.result().settled
    assert len(calls) == 1


def _process_spend(path, key):
    guard = SpendGuard(path)
    return guard.request("research-bot", "openai.com", 10, idempotency_key=key).status


def test_processes_share_atomic_budget(guard):
    from concurrent.futures import ProcessPoolExecutor
    with ProcessPoolExecutor(max_workers=3, mp_context=multiprocessing.get_context("spawn")) as pool:
        statuses = list(pool.map(_process_spend, [guard.db_path] * 10, map(str, range(10))))
    assert statuses.count("settled") == 5
    assert guard.status()["agents"][0]["spent"] == 50


def test_approval_rechecks_kill_and_commits_cancellation(guard):
    result = spend(guard, 40)
    with db.transaction(guard.db_path) as conn:
        conn.execute("UPDATE settings SET value='1' WHERE key='kill_switch_global'")
    with pytest.raises(InvalidState):
        guard.approve(result.request_id)
    assert guard.get(result.request_id).status == "cancelled"


def test_key_cannot_replay_another_agents_request(guard):
    original = spend(guard, key="shared")
    guard.create_agent("other", Policy(50, 100, 25, ["openai.com"]))
    replay = guard.request("other", "openai.com", 10, idempotency_key="shared")
    assert replay.decision == "deny" and replay.record is None
    assert len(guard.feed()) == 1
    assert guard.get(original.request_id) == original.record


def test_kill_between_reservation_and_execution(guard, monkeypatch):
    original_reserve = budget.reserve
    executions = []
    def reserve_then_kill(*args):
        result = original_reserve(*args)
        guard.kill()
        return result
    monkeypatch.setattr(budget, "reserve", reserve_then_kill)
    guard.executor = lambda req: executions.append(req)
    assert spend(guard).status == "cancelled"
    assert executions == []


def test_incompatible_schema_is_not_cleared(tmp_path):
    path = tmp_path / "old.db"
    with db.connection(path) as conn:
        conn.execute("CREATE TABLE agents (id TEXT PRIMARY KEY, legacy_field TEXT)")
        conn.execute("INSERT INTO agents VALUES ('existing', 'keep')")
        conn.commit()
    with pytest.raises(SpendGuardError, match="incompatible database schema"):
        SpendGuard(path)
    with db.connection(path) as conn:
        assert conn.execute("SELECT legacy_field FROM agents").fetchone()[0] == "keep"
