# SpendGuard library core

The migration is authored but **not executed or tested**, at the user's request.
Installation, import, build, integration, and concurrency checks remain pending.

## Installation and first request

Python 3.10+ is required. Commands for a later authorized validation session:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e .
# Only pytest is needed for core tests; dev also installs teammate extras.
.\.venv\Scripts\python -m pip install pytest
.\.venv\Scripts\python -m pytest -q
# Optional full development installation:
.\.venv\Scripts\python -m pip install -e ".[dev]"
```

```python
from spendguard import SpendGuard, Policy

sg = SpendGuard("spendguard.db")
sg.create_agent("research-bot", Policy(
    daily_budget=50, per_txn_cap=100, approval_threshold=25,
    allowlist=["openai.com", "serpapi.com", "aws.amazon.com"],
), name="Research Bot")
result = sg.request("research-bot", "openai.com", 10,
                    reason="Tool credits", idempotency_key="purchase-1")
print(result.decision, result.status, result.receipt_id)
```

The local fallback returns a mock receipt. No real payment integration is
implemented by the core. A new database starts with no agents; construction
creates tables and the initial global kill setting, and preserves existing data.
Use an explicit file path; `:memory:` is unsupported because each operation uses
its own connection. Existing databases from the previous design have an
incompatible agents schema: construction raises `SpendGuardError` without
clearing them. Keep that file and choose a new path for this library.

The core does not load `.env` or read environment configuration automatically.
`.env.example` lists integration settings `OPENAI_API_KEY`, `OPENAI_MODEL`, and
`SPENDGUARD_DB`. An integration can pass `os.getenv("SPENDGUARD_DB", "spendguard.db")`
to the constructor. Approval TTL is a constructor argument. The mock core needs
no credentials. Do not put live credentials in the committed example.

## Public API

`SpendGuard(db_path="spendguard.db", approval_ttl_seconds=300, executor=None,
explainer=None, on_hold=None)` owns configuration, not a persistent connection.
TTL must be finite and non-negative; zero permits immediate lazy expiry.
Timestamps use UTC `YYYY-MM-DDTHH:MM:SSZ`; fractional TTLs have second precision.

| Method | Return and behavior |
| --- | --- |
| `create_agent(agent_id, policy, name=None)` | `None`; upserts name and policy, preserving an existing killed status |
| `update_policy(agent_id, policy)` | `None`; `UnknownAgent` if absent |
| `request(agent_id, merchant, amount, reason="", idempotency_key=None)` | `Outcome`; ordinary input/internal errors fail closed without raising |
| `wait(request_id, timeout=300, interval=0.5)` | `RequestRecord`; polls until terminal or returns latest state on timeout |
| `get(request_id)` | `RequestRecord`; `NotFound` if absent |
| `pending()` | List of pending `RequestRecord`s, oldest first |
| `feed(limit=50)` | List of `RequestRecord`s, newest first; non-negative integer limit |
| `approve(request_id, approver="admin")` | `RequestRecord` after execution; `NotFound` / `InvalidState` on invalid transition |
| `reject(request_id, approver="admin")` | Rejected `RequestRecord`; same errors as approve |
| `kill(agent_id=None)` | `None`; globally or individually disables spending and cancels matching pending/approved records |
| `resume(agent_id=None)` | `None`; clears the selected kill state; never revives cancellations |
| `status()` | `{kill_global: bool, agents: [{id,name,status,daily_budget,spent,reserved,available}]}` |
| `reset()` | `None`; clears requests and kill state, keeps agents, names, and policies; `InvalidState` during execution |

Agent-specific kill/resume raise `UnknownAgent` for a missing agent. Configuration
and policy validation errors use `ValueError`; storage errors outside `request`
propagate. Reducing a policy budget below existing usage can make available funds
negative; existing approvals are not revoked. `reset()` is a deliberate local
demo reset, not a daily accounting operation.

Exports: `SpendGuard`, `Policy`, `RequestRecord`, `Outcome`, `SpendGuardError`,
`UnknownAgent`, `NotFound`, `InvalidState`, `RequestDenied`, `__version__` (0.1.0).
`governed` is exported only if Person C's `spendguard.tools` can be imported.
`RequestDenied(outcome)` exposes `.outcome`; the core does not raise it.

`Policy` is a dataclass with `daily_budget`, `per_txn_cap`, `approval_threshold`,
and `allowlist`. Limits must be finite and non-negative. Agent creation/update
stores a normalized copy of the allowlist.

`RequestRecord` is a dataclass containing `id,agent_id,merchant,amount,reason,
status,decision_reason,explanation,receipt_id,approver,created_at,decided_at,
expires_at,idempotency_key`. It supports `to_dict()` and `from_dict(d)`.

`Outcome` has `decision,status,reason,request_id,receipt_id,record`; `.settled`
is true exactly when status is `settled`. Pre-storage rejection has null record
and IDs. Persisted execution failures return `decision="deny"`, `status="failed"`.

Statuses: `allowed,executing,settled,failed,denied,pending_approval,approved,
rejected,expired,cancelled`. Terminal: `settled,failed,denied,rejected,expired,
cancelled`. Reserving: `allowed,executing,pending_approval,approved`. These tuples
are available from `spendguard.constants`.

## Policy and atomic reservation

The original pure policy evaluator is retained unchanged. First matching rule:
global kill, disabled agent, invalid amount, disallowed merchant, transaction
cap, remaining budget, approval threshold, allow. Threshold comparison is strict:
amount equal to the threshold is allowed. Hostnames are normalized to lowercase
without scheme/path/`www.` and checked by exact membership.

The original reservation flow remains one `BEGIN IMMEDIATE` transaction: lookup
idempotency, read agent/policy/ledger, evaluate, insert, commit. Each operation
uses a separate SQLite connection, foreign keys, WAL, and a five-second busy
timeout. Spent sums settled amounts, reserved sums reserving statuses, and
available is daily budget minus both, using the UTC creation date. Decimal
summation is retained; storage uses the specified REAL columns.

An omitted idempotency key generates a UUID. Replays return current saved state
without executing or notifying twice, even when the replay payload changes.
Keys are globally unique; reuse by a different agent fails closed. Lazy expiry
runs during reads, polling, decisions, status, and new reservations.

Execution is claimed once under a write lock after checking kill state, then
runs outside the transaction. Approvals re-check kill state and commit expiry or
cancellation before raising `InvalidState`. Transactions serialize writes across
threads and processes sharing a local database file.

## Adapters and background hooks

Supply `executor(request: dict)` returning
`{"ok": bool, "receipt_id": str | None, "detail": str}`. Its input contains exactly
`id,agent_id,merchant,amount,reason,idempotency_key`. Exceptions, false success,
or malformed results become failed requests, releasing their reservation.

Supply `explainer(request: dict, spent_today: float, daily_budget: float) -> str`
and optional `on_hold(record: RequestRecord)`. Each runs in its own daemon thread
after the hold commits. Neither delays the returned hold or affects the policy
decision; failures are ignored. A slow callback does not block the other.
Explanation text is stored only while the same request remains pending. Read it
with `get`; the initially returned Outcome is a snapshot and is not updated.

Defaults use guarded imports of Person B's `spendguard.adapters.execute` and
`spendguard.explain.explain`; import failures use deterministic local fallbacks.
Person B's CLI/dashboard and Person C's tools/examples remain outside this task.
The console entry point targets `spendguard.cli:main`, which will be available
when that teammate module exists. Package discovery includes their future
subpackages, and dashboard fixture JSON is configured as package data.

## Limitations and dependencies

Kill cannot undo external execution already in progress. A process crash after
claiming execution may leave a reservation requiring manual reconciliation;
there is no blind retry of an unknown external outcome. An error after a commit
can return a pre-storage-shaped denial even though a record was saved; inspect
using the original idempotency key before retrying a paid action. Reset is refused
while executing so it cannot erase a live reservation. Background workers may
be interrupted at process exit, and callbacks have no enforced timeout. Ledger
dates follow request creation even if approval occurs on a later UTC day.
SQLite uses a local file; no network filesystem coordination or access-control
boundary is supplied. Anyone with access to the database/library can administer it.

Core runtime dependencies: Python standard library only, including
[sqlite3](https://docs.python.org/3/library/sqlite3.html), dataclasses, threading,
and decimal. Packaging uses [setuptools](https://setuptools.pypa.io/).
Tests use [pytest](https://docs.pytest.org/). Optional extras use
[Streamlit](https://streamlit.io/) and the
[OpenAI Python SDK](https://github.com/openai/openai-python).
No public datasets or external project implementations were imported.
All runtime and packaging claims above describe authored behavior, pending validation.
