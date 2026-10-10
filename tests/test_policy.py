import pytest

from spendguard.policy import evaluate, normalize_merchant


@pytest.mark.parametrize("overrides,decision,reason", [
    ({}, "allow", "within policy"),
    ({"global_kill": True, "merchant": "bad.com"}, "deny", "kill switch active (global)"),
    ({"agent_status": "killed", "amount": -1}, "deny", "agent disabled or killed"),
    ({"amount": 0}, "deny", "invalid amount"),
    ({"amount": -1}, "deny", "invalid amount"),
    ({"amount": "10"}, "deny", "invalid amount"),
    ({"amount": True}, "deny", "invalid amount"),
    ({"amount": float("nan")}, "deny", "invalid amount"),
    ({"amount": float("inf")}, "deny", "invalid amount"),
    ({"merchant": "bad.com", "available": 0}, "deny", "merchant not allowed"),
    ({"amount": 100, "approval_threshold": 100}, "allow", "within policy"),
    ({"amount": 100.01}, "deny", "exceeds per-transaction cap"),
    ({"amount": 20, "available": 20}, "allow", "within policy"),
    ({"amount": 20.01, "available": 20}, "deny", "exceeds remaining budget"),
    ({"amount": 25}, "allow", "within policy"),
    ({"amount": 25.01}, "hold", "needs human approval"),
    ({"merchant": "https://WWW.OPENAI.COM/path"}, "allow", "within policy"),
    ({"merchant": "https://openai.com.evil.example"}, "deny", "merchant not allowed"),
])
def test_ordered_rules(overrides, decision, reason):
    args = dict(global_kill=False, agent_status="active", amount=10,
                merchant="openai.com", allowlist=["openai.com"],
                per_txn_cap=100, available=200, approval_threshold=25)
    result = evaluate(**(args | overrides))
    assert (result.decision, result.reason) == (decision, reason)


@pytest.mark.parametrize("merchant", ["", "https://[", "https://user@openai.com", "ftp://openai.com"])
def test_invalid_merchants(merchant):
    assert normalize_merchant(merchant) == ""
