# SpendGuard

A Python library for applying deterministic spend limits, merchant allowlists,
human approvals, and kill switches to AI agent requests. State is stored in
local SQLite. Python 3.10+ is required; the core has no third-party dependencies.

## Install

From this directory:

```powershell
python -m pip install .
```

Optional dashboard: `python -m pip install ".[dashboard]"`.
Optional OpenAI explanations: `python -m pip install ".[openai]"`.
Both extras: `python -m pip install ".[all]"`.

## Use

```python
from spendguard import SpendGuard, Policy

guard = SpendGuard("my-agent.db")
guard.create_agent(
    "research-bot",
    Policy(
        daily_budget=50,
        per_txn_cap=100,
        approval_threshold=25,
        allowlist=["openai.com", "aws.amazon.com"],
    ),
)

result = guard.request(
    "research-bot", "openai.com", 10,
    reason="Research credits", idempotency_key="purchase-001",
)
print(result.decision, result.status, result.receipt_id)
```

Decisions are `allow`, `hold`, or `deny`. Successful execution has status
`settled`. Requests over the approval threshold reserve funds while pending.
Use a unique idempotency key for each purchase and reuse it when retrying that
same purchase, so it is not executed twice.

Default adapters simulate payments for `openai.com`, `serpapi.com`, and
`aws.amazon.com`. No real payment occurs. Real integrations need an executor or
registered adapter that implements the paid operation; do not execute it a
second time after `request()` reports settlement.

## Approvals and controls

```python
held = guard.request("research-bot", "aws.amazon.com", 30,
                     reason="GPU credits", idempotency_key="purchase-002")
if held.decision == "hold":
    # A trusted human approval interface calls this after an actual decision.
    print(held.request_id)

print(guard.pending())
print(guard.status())
```

An approval interface calls `guard.approve(request_id, approver="reviewer")`
or `guard.reject(request_id, approver="reviewer")`. The requesting application
can poll with `guard.wait(request_id, timeout=120)` or read with `guard.get(id)`.
`guard.kill()` stops all agents; `guard.kill("research-bot")` stops one.
`guard.resume()` and `guard.resume("research-bot")` clear the selected kill state.
`guard.reset()` clears requests and kill state while retaining agents/policies;
it refuses reset during execution. Approval TTL defaults to 300 seconds and is
configurable through the constructor.

With the dashboard extra installed, open the same database:

```powershell
spendguard --db my-agent.db dashboard
```

Open http://localhost:8501. CLI commands include `status`, `feed`, `pending`,
`approve ID`, `reject ID`, `kill`, and `resume`.

## Integration and limits

`SpendGuard(db_path, executor=callback, explainer=callback, on_hold=callback)`
accepts optional integrations. Executors receive a dict containing
`id, agent_id, merchant, amount, reason, idempotency_key` and return
`{"ok": bool, "receipt_id": str | None, "detail": str}`. Explainers receive
`(request_dict, spent_today, daily_budget)` and return text. Explanation and
hold notification callbacks run in daemon threads; errors are ignored and their
output never controls policy decisions.

Optional OpenAI explanations use process environment variables `OPENAI_API_KEY`
and `OPENAI_MODEL` (default `gpt-4o-mini`). Without a key, SDK, or successful call,
the explainer returns a local template. Environment files are not loaded
automatically. CLI/dashboard database selection uses `SPENDGUARD_DB` or `--db`;
Python callers pass the path to the constructor.

SpendGuard is a trusted local library, without an authentication boundary.
Processes must share the same local database to share state. Custom executors
and adapter registrations are process-local and must be configured in any
process performing approvals; the stock dashboard/CLI uses default adapters.
Kill cannot undo an action already executing. Interrupted execution may require
manual reconciliation. Daily accounting follows UTC request creation dates.
Constructing a guard preserves data, but incompatible older database schemas
require a separate database file. This is a prototype; a passing test suite
does not validate real-payment integration or an interactive deployment.

## Build a distribution

This directory is self-contained. To create wheel and source archives:

```powershell
python -m pip install build
python -m build
```

Artifacts appear in `dist/`. The installation name is `[project].name` in
`pyproject.toml`; the Python import remains `spendguard` unless its source and
imports are renamed. Publishing to a package index is a separate step.
