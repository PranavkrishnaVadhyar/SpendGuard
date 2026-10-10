"""Create the repeatable local data used by the SpendGuard demos."""

from __future__ import annotations

import os


def ensure_demo_agent(guard) -> None:
    """Create or refresh the fixed policy used by every local demo."""
    from spendguard import Policy

    policy = Policy(
        daily_budget=50,
        per_txn_cap=100,
        approval_threshold=25,
        allowlist=["openai.com", "serpapi.com", "aws.amazon.com"],
    )
    try:
        guard.create_agent("research-bot", policy, name="Research bot")
    except Exception:
        # Cores that model create as insert-only can still seed repeatedly.
        if not any(agent.get("id") == "research-bot" for agent in guard.status().get("agents", [])):
            raise


def main() -> None:
    from spendguard import SpendGuard

    database = os.getenv("SPENDGUARD_DB", "spendguard.db")
    guard = SpendGuard(db_path=database)
    ensure_demo_agent(guard)
    print(f"Demo agent is ready in {database}")


if __name__ == "__main__":
    main()
