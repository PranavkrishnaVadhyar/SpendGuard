# SpendGuard pitch

Agents can move from a prompt to a purchase faster than a human can intervene.
SpendGuard is a local Python library that makes policy enforcement part of the
tool boundary: every spend is allowed, held for review, or denied before an
executor can act.

The core uses SQLite and the standard library for a portable audit trail of
requests, decisions, approvals, and receipts. Agents receive neither payment
credentials nor direct egress. A governed function calls the local policy
store first; if the store is unavailable or the decision is not settled, the
side effect does not run.

The demo research agent encounters a poisoned page telling it to buy gift
cards. Its governed purchase tool denies the unapproved merchant even if an
LLM repeats the malicious instruction. Larger allowed purchases become holds
that a human can approve in code, with the CLI, or in a dashboard.

SpendGuard is intentionally an authorization and audit layer, not a payment
processor. Executors can integrate with a real provider only after settlement,
while the library preserves idempotency, budget reservation, kill switches,
and reviewable policy decisions.
