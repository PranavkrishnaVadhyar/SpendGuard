from concurrent.futures import ThreadPoolExecutor

import pytest

from spendguard import SpendGuard, Policy, budget, db


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "test.db"
    guard = SpendGuard(path)
    guard.create_agent("research-bot", Policy(50, 100, 25, ["openai.com"]))
    return path


def reserve(database, key, amount=10):
    return budget.reserve(database, "research-bot", "openai.com", amount, "test", key)


def test_parallel_budget(database):
    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(lambda n: reserve(database, str(n)), range(20)))
    assert sum(row["status"] == "allowed" for row, _ in results) == 5
    with db.connection(database) as conn:
        balances = budget.ledger(conn, "research-bot", db.now())
    assert balances["spent"] + balances["reserved"] == 50
    assert balances["available"] == 0


def test_concurrent_idempotency(database):
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: reserve(database, "same"), range(8)))
    assert len({row["id"] for row, _ in results}) == 1
    assert sum(created for _, created in results) == 1
    with db.connection(database) as conn:
        assert conn.execute("SELECT COUNT(*) FROM requests").fetchone()[0] == 1


def test_replay_unchanged(database):
    first, created = reserve(database, "same")
    replay, created_again = reserve(database, "same", 40)
    assert created and not created_again
    assert replay == first


def test_old_day_excluded(database):
    reserve(database, "yesterday", 40)
    with db.transaction(database) as conn:
        conn.execute("UPDATE requests SET created_at='2000-01-01T00:00:00Z',status='settled'")
    row, _ = reserve(database, "today", 40)
    assert row["status"] == "pending_approval"


def test_expiry_releases_reservation(database):
    reserve(database, "expired", 40)
    with db.transaction(database) as conn:
        conn.execute("UPDATE requests SET expires_at='2000-01-01T00:00:00Z'")
    row, _ = reserve(database, "new", 40)
    assert row["status"] == "pending_approval"


def test_default_keys_are_unique(database):
    first, _ = reserve(database, None)
    second, _ = reserve(database, None)
    assert first["id"] != second["id"]
    assert first["idempotency_key"] != second["idempotency_key"]
