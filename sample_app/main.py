"""Example consumer of the installed SpendGuard package."""

import argparse
from pathlib import Path

from spendguard import Outcome, Policy, SpendGuard


DATABASE = Path(__file__).resolve().with_name("sample.db")
AGENT_ID = "sample-research-bot"


def explain_request(request: dict, spent_today: float, daily_budget: float) -> str:
    """Keep this example local and usable without external API credentials."""
    return (
        f"{request['reason']}: ${request['amount']:.2f} at {request['merchant']}. "
        f"Settled spending today is ${spent_today:.2f} of ${daily_budget:.2f}."
    )


def show_result(label: str, outcome: Outcome) -> None:
    print(f"\n{label}: {outcome.decision} / {outcome.status}")
    print(f"  Request ID: {outcome.request_id}")
    print(f"  Reason: {outcome.reason}")
    if outcome.receipt_id:
        print(f"  Mock receipt: {outcome.receipt_id}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="Clear this sample's requests and kill state")
    parser.add_argument("--wait", action="store_true", help="Wait up to two minutes for the held request to finish")
    args = parser.parse_args()

    guard = SpendGuard(DATABASE, approval_ttl_seconds=1800, explainer=explain_request)
    if args.reset:
        guard.reset()
    guard.create_agent(
        AGENT_ID,
        Policy(
            daily_budget=50,
            per_txn_cap=100,
            approval_threshold=25,
            allowlist=["openai.com", "aws.amazon.com"],
        ),
        name="Sample Research Bot",
    )

    print(f"Database: {DATABASE}")
    print("Payments use the package's default mock adapters.")

    allowed = guard.request(
        AGENT_ID, "openai.com", 10, reason="Summarize research papers",
        idempotency_key="sample-summary-1",
    )
    show_result("Small purchase", allowed)

    held = guard.request(
        AGENT_ID, "aws.amazon.com", 30, reason="Purchase GPU credits",
        idempotency_key="sample-gpu-1",
    )
    show_result("Purchase requiring approval", held)

    denied = guard.request(
        AGENT_ID, "openai.com", 99, reason="Purchase beyond the available budget",
        idempotency_key="sample-over-budget-1",
    )
    show_result("Over-budget purchase", denied)

    if any(result.request_id is None for result in (allowed, held, denied)):
        print("\nA request could not be stored. Check the database path and policy configuration.")
        return 1

    if args.wait and held.status == "pending_approval":
        print("\nApprove or reject the held request in the dashboard. Waiting up to 120 seconds...")
        record = guard.wait(held.request_id, timeout=120, interval=0.5)
        print(f"Request {record.id}: {record.status}")
        if record.status == "pending_approval":
            print("Still pending; the wait timed out. The reservation remains until a decision or expiry.")

    agent = next(item for item in guard.status()["agents"] if item["id"] == AGENT_ID)
    print(
        f"\nBudget: spent ${agent['spent']:.2f}, reserved ${agent['reserved']:.2f}, "
        f"available ${agent['available']:.2f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
