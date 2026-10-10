"""Deterministic local attack scenarios for SpendGuard."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable


@dataclass(frozen=True)
class ScenarioResult:
    name: str
    passed: bool
    detail: str


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _agent_totals(guard: Any) -> tuple[float, float]:
    agent = next(agent for agent in guard.status()["agents"] if agent["id"] == "research-bot")
    return float(agent["spent"]), float(agent["reserved"])


def scenario_1_allowed(factory: Any) -> None:
    guard = factory.fresh()
    outcome = guard.request("research-bot", "serpapi.com", 2, "search")
    _require(outcome.decision == "allow" and outcome.settled, "allowed request did not settle")
    _require(bool(outcome.receipt_id), "allowed request has no receipt")


def scenario_2_approval(factory: Any) -> None:
    guard = factory.fresh()
    outcome = guard.request("research-bot", "aws.amazon.com", 40, "compute")
    _require(outcome.decision == "hold", "threshold request was not held")
    guard.approve(outcome.request_id, approver="admin")
    record = guard.wait(outcome.request_id, timeout=1, interval=0.01)
    _require(record.status == "settled", "approved request did not settle")


def scenario_3_allowlist(factory: Any) -> None:
    guard = factory.fresh()
    outcome = guard.request("research-bot", "giftcard.example", 30, "gift cards")
    _require(outcome.decision == "deny", "disallowed merchant was not denied")
    _require(outcome.reason == "merchant not allowed", "wrong allowlist reason")


def scenario_4_parallel_reservation(factory: Any) -> None:
    guard = factory.fresh()
    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(
            executor.map(
                lambda _: guard.request("research-bot", "openai.com", 30, "parallel"),
                range(2),
            )
        )
    _require(sum(outcome.decision == "hold" for outcome in outcomes) == 1, "expected one hold")
    _require(sum(outcome.decision == "deny" for outcome in outcomes) == 1, "expected one denial")
    spent, reserved = _agent_totals(guard)
    _require(spent + reserved <= 50, "parallel requests over-reserved the budget")


def scenario_5_idempotency(factory: Any) -> None:
    guard = factory.fresh()
    first = guard.request("research-bot", "serpapi.com", 2, "search", "repeatable-search")
    second = guard.request("research-bot", "serpapi.com", 2, "search", "repeatable-search")
    _require(first.request_id == second.request_id, "idempotency key created two requests")
    _require(len(guard.feed(limit=50)) == 1, "idempotency key created two feed entries")
    spent, _ = _agent_totals(guard)
    _require(spent == 2, "idempotent request spent more than once")


def scenario_6_budget_race(factory: Any) -> None:
    guard = factory.fresh()
    with ThreadPoolExecutor(max_workers=16) as executor:
        outcomes = list(
            executor.map(
                lambda _: guard.request("research-bot", "openai.com", 1, "rapid"),
                range(100),
            )
        )
    _require(sum(outcome.settled for outcome in outcomes) == 50, "expected 50 settled requests")
    _require(sum(outcome.decision == "deny" for outcome in outcomes) == 50, "expected 50 denials")
    spent, _ = _agent_totals(guard)
    _require(spent == 50, "rapid requests exceeded or underused the budget")


def scenario_7_kill_switch(factory: Any) -> None:
    guard = factory.fresh()
    held = guard.request("research-bot", "aws.amazon.com", 40, "compute")
    _require(held.decision == "hold", "request was not held before kill")
    guard.kill()
    record = guard.wait(held.request_id, timeout=1, interval=0.01)
    _require(record.status == "cancelled", "kill did not cancel held request")
    outcome = guard.request("research-bot", "serpapi.com", 1, "after kill")
    _require(outcome.decision == "deny", "global kill did not deny new request")
    _require(outcome.reason == "kill switch active (global)", "wrong kill-switch reason")
    guard.resume()


def scenario_8_transaction_cap(factory: Any) -> None:
    guard = factory.fresh()
    outcome = guard.request("research-bot", "serpapi.com", 150, "oversized search")
    _require(outcome.decision == "deny", "over-cap request was not denied")
    _require(outcome.reason == "exceeds cap", "wrong transaction-cap reason")


def scenario_9_multi_instance(factory: Any) -> None:
    first = factory.fresh()
    held = first.request("research-bot", "aws.amazon.com", 40, "compute")
    _require(held.decision == "hold", "shared request was not held")
    second = factory.peer(first)
    second.approve(held.request_id, approver="second-instance")
    record = first.wait(held.request_id, timeout=1, interval=0.01)
    _require(record.status == "settled", "second instance approval was not observed")


SCENARIOS: list[tuple[str, Callable[[Any], None]]] = [
    ("1. Allowlisted request settles", scenario_1_allowed),
    ("2. Threshold request needs approval", scenario_2_approval),
    ("3. Allowlist blocks gift cards", scenario_3_allowlist),
    ("4. Parallel holds reserve once", scenario_4_parallel_reservation),
    ("5. Idempotency spends once", scenario_5_idempotency),
    ("6. Rapid requests cannot exceed budget", scenario_6_budget_race),
    ("7. Global kill cancels and blocks", scenario_7_kill_switch),
    ("8. Per-transaction cap blocks", scenario_8_transaction_cap),
    ("9. Second instance can approve", scenario_9_multi_instance),
]


def run_scenarios(factory: Any) -> list[ScenarioResult]:
    results = []
    for name, scenario in SCENARIOS:
        try:
            scenario(factory)
        except Exception as exc:
            results.append(ScenarioResult(name, False, str(exc)))
        else:
            results.append(ScenarioResult(name, True, "verified"))
    return results


def write_results(results: list[ScenarioResult], path: Path) -> None:
    lines = [
        "# Attack-suite results",
        "",
        "Generated by `python examples/attacks.py` against the local SpendGuard library.",
        "",
        "| Scenario | Result | Detail |",
        "| --- | --- | --- |",
    ]
    for result in results:
        state = "PASS" if result.passed else "FAIL"
        lines.append(f"| {result.name} | {state} | {result.detail} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class LocalFactory:
    """Creates isolated, real SQLite-backed guards for the command-line suite."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self._paths: dict[int, Path] = {}
        self._counter = 0

    def fresh(self):
        from spendguard import Policy, SpendGuard

        self._counter += 1
        path = self.directory / f"scenario-{self._counter}.db"
        guard = SpendGuard(db_path=str(path))
        guard.create_agent(
            "research-bot",
            Policy(
                daily_budget=50,
                per_txn_cap=100,
                approval_threshold=25,
                allowlist=["openai.com", "serpapi.com", "aws.amazon.com"],
            ),
            name="Research bot",
        )
        self._paths[id(guard)] = path
        return guard

    def peer(self, guard):
        from spendguard import SpendGuard

        return SpendGuard(db_path=str(self._paths[id(guard)]))


def main() -> int:
    with TemporaryDirectory(prefix="spendguard-attacks-") as temporary:
        results = run_scenarios(LocalFactory(Path(temporary)))
    write_results(results, Path(__file__).parents[1] / "docs" / "results.md")
    for result in results:
        print(f"{'PASS' if result.passed else 'FAIL'}: {result.name} — {result.detail}")
    return 0 if all(result.passed for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
