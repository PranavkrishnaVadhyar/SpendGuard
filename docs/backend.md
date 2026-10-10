# SpendGuard backend

Implementation is written but has **not been run or tested**, at the user's request.
The following commands are instructions for a later authorized validation session.

## Setup and commands

Use Python 3.11+ from the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python -m uvicorn gateway.main:app --reload --port 8000
```

Tests, when authorized: `.\.venv\Scripts\python -m pytest -q`.
Do not overwrite an existing `.env`. Set `ADMIN_KEY` before exposing the service;
the supplied key is a local demo default. `DB_PATH` selects the SQLite file.
`APPROVAL_TTL_SECONDS` defaults to 300 and must be positive.
Startup creates the schema, seeds Research Bot when no agents exist, and writes
a random bearer token to the ignored repository-root `.demo_token` file.
Only its SHA-256 hash is stored in SQLite. Reset reuses that file.

## HTTP contract

Agents send `Authorization: Bearer <contents of .demo_token>`; administrators send
`X-Admin-Key: <ADMIN_KEY>`. Never publish either credential.

| Endpoint | Input / response |
| --- | --- |
| `GET /health` | Public; `{ok:true}` |
| `POST /request` | Agent; `{merchant,amount,reason,idempotency_key}` → `{request_id,decision,status,reason,receipt_id}` |
| `GET /requests/{id}` | Agent; own request record, otherwise 404 |
| `GET /feed?limit=50` | Admin; `{kill_global,agents,requests}`, newest requests first; limit 1–1000 |
| `GET /pending` | Admin; `{requests}` containing pending approvals |
| `POST /approvals/{id}` | Admin; `{approve:boolean,approver:string}` → request record |
| `POST /kill` | Admin; `{scope:"global"}` or `{scope:"agent",agent_id}` → `{ok:true}` |
| `POST /resume` | Admin; same scope input → `{ok:true}` |
| `POST /reset` | Admin; reset seed and clear requests → `{ok:true}` |

Request records have `id, agent_id, merchant, amount, reason, status,
decision_reason, explanation, receipt_id, approver, created_at, decided_at,
expires_at`. All timestamps are UTC `YYYY-MM-DDTHH:MM:SSZ`.
Agent summaries expose `id,name,status,daily_budget,spent,reserved,available`.
Authentication failures are 401 for agents and 403 for administrators;
unknown resources are 404 and invalid transitions 409.
Malformed `/request` bodies and unexpected processing errors return HTTP 200
with `decision:"deny"`, `status:"denied"`, null request/receipt IDs and a short
sanitized reason. A persisted executor failure instead returns its request ID
and `status:"failed"`. Other endpoints use FastAPI validation errors (422).

## Enforcement and reservations

Pure policy rules are evaluated in this order: global kill, disabled agent,
invalid amount, disallowed merchant, transaction cap, remaining budget,
approval threshold, allow. Hostnames are lowercased and scheme/`www.` removed;
allowlist matching uses exact hostnames, never suffix matching.
Seed limits are $50 per UTC day, $100 per transaction, and approval above $25;
allowed merchants are `openai.com`, `serpapi.com`, `aws.amazon.com`.

One SQLite `BEGIN IMMEDIATE` transaction checks idempotency, reads policy and
the daily ledger, evaluates, and inserts the reservation. Each call opens its
own connection with a five-second busy timeout; the database uses WAL mode.
Spent is the sum of settled requests; reserved sums allowed, executing,
pending_approval, and approved requests by the UTC date of creation. Available
is budget minus both sums. Decimal summation avoids binary addition drift;
storage retains the specified REAL schema. No ledger table is used.

The idempotency key is globally unique. Replays return the existing request's
current state without re-executing, even if the replay payload changes. A key
owned by another agent fails closed without revealing the other request.
Execution is claimed under a write lock, with a fresh kill check, before the
external function runs outside the transaction. Approval expiry is applied
lazily on reads, approvals, and new reservations. Kill cancels matching pending
and approved requests; resume never revives cancelled requests.

## Integration and limitations

Person B supplies `gateway.executor.execute(request)` and
`gateway.explainer.explain(request, spent_today, daily_budget)`. The executor
receives `id,agent_id,merchant,amount,reason,idempotency_key` and returns
`{ok:boolean,receipt_id:string|null,detail:string}`. The explainer returns text.
Import failures use the specified local mock receipt and deterministic text
fallbacks. No LLM or real payment code is implemented here. Execution exceptions
or `ok:false` release reservations as failed; explanation exceptions are ignored.
Explanation text has no influence on policy decisions.

Kill cannot undo an already executing external action. Reset returns 409 while
execution is in progress to avoid losing its reservation. A crash after claiming
execution can leave funds reserved; there is no automatic recovery or retry
because the external outcome may be unknown. Unexpected failures after a commit
can produce a deny response while the saved request remains reserved or settled;
retry the same idempotency key to inspect its state, never a new key blindly.
The ledger follows creation date even across midnight. Calls to teammate modules
are synchronous worker-thread calls with no enforced timeout. The demo token is
plaintext on disk; protect the local filesystem. This is a local mock-payment
prototype, with runtime/concurrency/integration verification still pending.

## Dependencies and sources

Backend: [FastAPI](https://fastapi.tiangolo.com/),
[Uvicorn](https://www.uvicorn.org/), [Pydantic](https://docs.pydantic.dev/),
[python-dotenv](https://github.com/theskumar/python-dotenv), and Python's standard
[sqlite3](https://docs.python.org/3/library/sqlite3.html).
Tests use [pytest](https://docs.pytest.org/) and [HTTPX](https://www.python-httpx.org/).
Shared team requirements include [Streamlit](https://streamlit.io/),
[OpenAI Python SDK](https://github.com/openai/openai-python), and
[RESPX](https://lundberg.github.io/respx/). No public dataset or external project
implementation was imported. Dependencies are not fully pinned; compatibility
must be verified when installation and execution are authorized.
