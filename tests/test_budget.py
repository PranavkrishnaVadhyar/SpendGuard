from concurrent.futures import ThreadPoolExecutor

import pytest

from gateway import budget, db
from gateway.models import SpendRequest


@pytest.fixture
def database(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(db, "TOKEN_PATH", tmp_path / ".demo_token")
    db.initialize()


def reserve(key, amount=10):
    return budget.reserve("research-bot", SpendRequest(
        merchant="openai.com", amount=amount, reason="test", idempotency_key=key))


def test_parallel_budget(database):
    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(lambda n: reserve(str(n)), range(20)))
    assert sum(row["status"] == "allowed" for row, _ in results) == 5
    with db.connection() as conn:
        balances = budget.ledger(conn, "research-bot", db.now())
    assert balances["spent"] + balances["reserved"] == 50
    assert balances["available"] == 0


def test_concurrent_idempotency(database):
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: reserve("same"), range(8)))
    assert len({row["id"] for row, _ in results}) == 1
    assert sum(created for _, created in results) == 1
    with db.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM requests").fetchone()[0] == 1


def test_replay_unchanged(database):
    first, created = reserve("same")
    replay, created_again = reserve("same", 40)
    assert created and not created_again
    assert replay == first


def test_old_day_excluded(database):
    reserve("yesterday", 40)
    with db.transaction() as conn:
        conn.execute("UPDATE requests SET created_at='2000-01-01T00:00:00Z',status='settled'")
    row, _ = reserve("today", 40)
    assert row["status"] == "pending_approval"


def test_expiry_releases_reservation(database):
    reserve("expired", 40)
    with db.transaction() as conn:
        conn.execute("UPDATE requests SET expires_at='2000-01-01T00:00:00Z'")
    row, _ = reserve("new", 40)
    assert row["status"] == "pending_approval"
