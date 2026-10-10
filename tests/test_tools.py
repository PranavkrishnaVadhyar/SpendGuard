from dataclasses import dataclass

import pytest

from spendguard.tools import RequestDenied, governed


@dataclass
class Outcome:
    decision: str
    status: str
    reason: str = "within policy"
    request_id: str = "request-1"
    receipt_id: str | None = "receipt-1"

    @property
    def settled(self):
        return self.status == "settled"


@dataclass
class Record:
    status: str
    decision_reason: str
    receipt_id: str | None = "receipt-1"


class FakeGuard:
    def __init__(self, outcome=None, record=None, request_error=None, wait_error=None):
        self.outcome = outcome or Outcome("allow", "settled")
        self.record = record or Record("settled", "within policy")
        self.request_error = request_error
        self.wait_error = wait_error
        self.requests = []

    def request(self, *args):
        self.requests.append(args)
        if self.request_error:
            raise self.request_error
        return self.outcome

    def wait(self, request_id, timeout):
        if self.wait_error:
            raise self.wait_error
        self.wait_request_id = request_id
        self.wait_timeout = timeout
        return self.record


def test_settled_request_runs_the_wrapped_function():
    guard = FakeGuard()

    @governed(guard, "bot", "openai.com", amount=2, reason="research")
    def purchase():
        return "purchased"

    assert purchase() == "purchased"
    assert guard.requests[0][:4] == ("bot", "openai.com", 2, "research")


def test_none_result_is_replaced_with_receipt():
    guard = FakeGuard()

    @governed(guard, "bot", "openai.com", amount=2)
    def purchase():
        return None

    assert purchase() == {"ok": True, "receipt_id": "receipt-1"}


def test_denial_does_not_run_wrapped_function():
    guard = FakeGuard(Outcome("deny", "denied", "merchant not allowed"))
    called = False

    @governed(guard, "bot", "giftcard.example", amount=2)
    def purchase():
        nonlocal called
        called = True

    assert purchase() == {"error": "denied", "reason": "merchant not allowed"}
    assert not called


def test_denial_can_raise_library_error():
    guard = FakeGuard(Outcome("deny", "denied", "merchant not allowed"))

    @governed(guard, "bot", "giftcard.example", amount=2, raise_on_deny=True)
    def purchase():
        raise AssertionError("must not execute")

    with pytest.raises(RequestDenied):
        purchase()


def test_held_request_runs_after_settlement():
    guard = FakeGuard(
        Outcome("hold", "pending", "needs human approval"),
        Record("settled", "within policy", "receipt-2"),
    )

    @governed(guard, "bot", "aws.amazon.com", amount=40, wait_timeout=12)
    def purchase():
        return "settled later"

    assert purchase() == "settled later"
    assert guard.wait_request_id == "request-1"
    assert guard.wait_timeout == 12


def test_held_request_reports_rejection_without_running():
    guard = FakeGuard(
        Outcome("hold", "pending", "needs human approval"),
        Record("rejected", "reviewer rejected"),
    )
    called = False

    @governed(guard, "bot", "aws.amazon.com", amount=40)
    def purchase():
        nonlocal called
        called = True

    assert purchase() == {"error": "rejected", "reason": "reviewer rejected"}
    assert not called


def test_held_request_timeout_is_fail_closed():
    guard = FakeGuard(
        Outcome("hold", "pending", "needs human approval"),
        Record("pending", "needs human approval"),
    )

    @governed(guard, "bot", "aws.amazon.com", amount=40)
    def purchase():
        raise AssertionError("must not execute")

    assert purchase() == {"error": "timeout", "reason": "needs human approval"}


def test_guard_failures_are_fail_closed():
    guard = FakeGuard(request_error=RuntimeError("database unavailable"))

    @governed(guard, "bot", "openai.com", amount=2)
    def purchase():
        raise AssertionError("must not execute")

    assert purchase() == {"error": "guard_unavailable"}


def test_metadata_amount_and_idempotency_override():
    guard = FakeGuard()

    @governed(guard, "bot", "openai.com", amount=None)
    def purchase(amount):
        """Buy the requested amount."""
        return amount

    assert purchase.__name__ == "purchase"
    assert purchase.__doc__ == "Buy the requested amount."
    assert purchase(3, _idempotency_key="same-key") == 3
    assert purchase(3, _idempotency_key="same-key") == 3
    assert guard.requests[0][-1] == guard.requests[1][-1] == "same-key"

    purchase(3)
    purchase(3)
    assert guard.requests[2][-1] != guard.requests[3][-1]
