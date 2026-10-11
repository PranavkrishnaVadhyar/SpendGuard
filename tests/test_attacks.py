import importlib.util
import sys
import threading
from dataclasses import dataclass
from pathlib import Path


def _load_attacks():
    path = Path(__file__).parents[1] / "examples" / "attacks.py"
    spec = importlib.util.spec_from_file_location("spendguard_attacks", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@dataclass
class FakeRecord:
    id: str
    status: str
    decision_reason: str
    amount: float
    receipt_id: str | None = None


@dataclass
class FakeOutcome:
    decision: str
    status: str
    reason: str
    request_id: str
    receipt_id: str | None = None

    @property
    def settled(self):
        return self.status == "settled"


class FakeState:
    def __init__(self):
        self.lock = threading.Lock()
        self.records = {}
        self.idempotency = {}
        self.spent = 0.0
        self.reserved = 0.0
        self.kill_global = False
        self.counter = 0


class FakeGuard:
    def __init__(self, state=None):
        self.state = state or FakeState()

    def _outcome(self, record, decision):
        return FakeOutcome(
            decision,
            record.status,
            record.decision_reason,
            record.id,
            record.receipt_id,
        )

    def request(self, agent_id, merchant, amount, reason="", idempotency_key=None):
        with self.state.lock:
            if idempotency_key and idempotency_key in self.state.idempotency:
                record = self.state.records[self.state.idempotency[idempotency_key]]
                decision = "allow" if record.status == "settled" else "hold"
                return self._outcome(record, decision)
            self.state.counter += 1
            request_id = f"request-{self.state.counter}"
            if self.state.kill_global:
                return FakeOutcome("deny", "denied", "kill switch active (global)", request_id)
            if merchant not in {"openai.com", "serpapi.com", "aws.amazon.com"}:
                return FakeOutcome("deny", "denied", "merchant not allowed", request_id)
            if amount > 100:
                return FakeOutcome("deny", "denied", "exceeds cap", request_id)
            if self.state.spent + self.state.reserved + amount > 50:
                return FakeOutcome("deny", "denied", "exceeds remaining", request_id)
            if amount >= 25:
                record = FakeRecord(request_id, "pending", "needs human approval", amount)
                self.state.reserved += amount
                decision = "hold"
            else:
                record = FakeRecord(
                    request_id,
                    "settled",
                    "within policy",
                    amount,
                    f"receipt-{request_id}",
                )
                self.state.spent += amount
                decision = "allow"
            self.state.records[request_id] = record
            if idempotency_key:
                self.state.idempotency[idempotency_key] = request_id
            return self._outcome(record, decision)

    def approve(self, request_id, approver="admin"):
        with self.state.lock:
            record = self.state.records[request_id]
            if record.status == "pending":
                self.state.reserved -= record.amount
                self.state.spent += record.amount
                record.status = "settled"
                record.decision_reason = "within policy"
                record.receipt_id = f"receipt-{request_id}"

    def wait(self, request_id, timeout=300, interval=0.5):
        return self.state.records[request_id]

    def feed(self, limit=50):
        return list(self.state.records.values())[-limit:]

    def pending(self):
        return [record for record in self.state.records.values() if record.status == "pending"]

    def kill(self, agent_id=None):
        with self.state.lock:
            self.state.kill_global = True
            for record in self.state.records.values():
                if record.status == "pending":
                    self.state.reserved -= record.amount
                    record.status = "cancelled"
                    record.decision_reason = "kill switch active (global)"

    def resume(self, agent_id=None):
        self.state.kill_global = False

    def status(self):
        return {
            "kill_global": self.state.kill_global,
            "agents": [
                {
                    "id": "research-bot",
                    "name": "Research bot",
                    "status": "active",
                    "daily_budget": 50,
                    "spent": self.state.spent,
                    "reserved": self.state.reserved,
                    "available": 50 - self.state.spent - self.state.reserved,
                }
            ],
        }


class FakeFactory:
    def fresh(self):
        return FakeGuard()

    def peer(self, guard):
        return FakeGuard(guard.state)


def test_all_documented_attack_scenarios_pass_with_the_fake_core():
    attacks = _load_attacks()
    results = attacks.run_scenarios(FakeFactory())
    assert len(results) == 9
    assert all(result.passed for result in results), results
