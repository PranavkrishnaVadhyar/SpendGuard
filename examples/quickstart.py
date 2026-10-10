"""A small local SpendGuard example."""

from spendguard import Policy, SpendGuard
from spendguard.tools import governed


guard = SpendGuard(db_path="spendguard.db")
policy = Policy(
    daily_budget=5,
    per_txn_cap=5,
    approval_threshold=5,
    allowlist=["openai.com"],
)
guard.create_agent("quickstart", policy, name="Quickstart agent")


@governed(guard, "quickstart", "openai.com", amount=2, reason="research")
def buy_research() -> str:
    return "research purchased"


print(buy_research())
print(buy_research())
print(guard.request("quickstart", "giftcards.example", 1, "gift card"))
