# SpendGuard — spnd-guard

SpendGuard is a Python library that puts spending controls around AI agent
actions. Your application defines budgets, permitted merchants, and approval
thresholds; SpendGuard checks each paid operation before allowing it to run.
Requests live in SQLite, with a local dashboard for reviewing spending,
approving purchases, and stopping further activity.

**Distribution:** `spnd-guard` · **Import:** `spendguard` ·
**CLI:** `spendguard` · **Version:** `0.1.0` · **Python:** `3.10+`

Default payment adapters and sample credit purchases are simulations. The
LangChain chatbot can make real model API calls using your provider account.

## Why use it?

An agent with a paid tool can repeatedly buy credits or consume services.
SpendGuard gives the application a consistent place to enforce limits and
require human review before executing that tool.

| Without application spending controls | With SpendGuard integrated |
| --- | --- |
| Each paid tool needs its own budget checks | One policy controls declared tool costs |
| Expensive purchases can execute immediately | Purchases above a threshold wait for approval |
| Concurrent calls compete for the same balance | SQLite transactions reserve agent and team funds |
| A retry can execute another purchase | The same idempotency key returns saved state/results |
| Activity is scattered across tool logs | Requests, usage, and workflow events share a dashboard |

Only operations routed through SpendGuard are controlled. Model usage tracking
is after-response accounting; it does not stop an in-flight model call.

## Features

- Per-agent daily budgets, transaction caps, and merchant allowlists.
- Human approval with expiring holds and reserved funds.
- Shared team budgets with atomic reservations and membership snapshots.
- Global and per-agent kill switches, plus resume controls.
- Idempotent requests, stored results, and a durable request feed.
- Optional LangChain wrappers for synchronous `StructuredTool` tools.
- Model token tracking and cost estimates using configured rates.
- Workflow/session tracing for models, tools, and purchase transitions.
- Streamlit dashboard for approvals, usage, workflows, teams, and email.
- Email outbox with explicit SMTP send/retry and budget warnings.
- A core library with no third-party runtime dependencies.

## Installation

From a source checkout, in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dashboard,langchain]"
```

For just the core, install with `-e .`. Other extras are `openai`, `all`, and
the repository's `dev` extra. Install your model-provider integration separately;
the chatbot requirements below include `langchain-openai`.

The prepared PyPI name is `spnd-guard`. Publication has not been verified in
this repository's validation record. Once available on PyPI, consumers can use:

```powershell
python -m pip install "spnd-guard[langchain,dashboard]"
```

Use a fresh environment when switching from the earlier local `spendguard`
distribution: both install the same Python modules and CLI. If Windows locks
`spendguard.exe` during reinstall, close processes using it first.

## Use the library

```python
from spendguard import Policy, SpendGuard

guard = SpendGuard("agent.db")
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
    reason="Research credits", idempotency_key="research-purchase-001",
)
print(result.decision, result.status, result.receipt_id)
```

Decisions are `allow`, `hold`, or `deny`. Only `settled` means execution
succeeded. Held requests reserve funds while awaiting human approval.
Reuse a purchase's key for retries; use a new key for an independent purchase.

Default adapters simulate payments to `openai.com`, `serpapi.com`, and
`aws.amazon.com`. Supply a real executor or wrap your actual paid operation
to integrate a provider. Do not execute the purchase again after settlement.
See [the core API guide](docs/core.md) and [LangChain integration](docs/langchain.md).

## Run the LangChain chatbot

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pip install -r sample_app\requirements-chatbot.txt
# First-time configuration; preserve an existing .env:
if (-not (Test-Path sample_app\.env)) { Copy-Item sample_app\.env.example sample_app\.env }
```

Edit the ignored `sample_app/.env` with `OPENAI_API_KEY` and `OPENAI_MODEL`,
then start the chatbot:

```powershell
.\.venv\Scripts\python.exe sample_app\chatbot.py
```

Try `Buy 1 demo credit` or `Buy 3 demo credits`. The application generates a
random UUID order ID for a new purchase; users do not need to invent one.
The returned ID is reused for retries and retained through approval/resume.
Omitting an ID again creates a new purchase.

Each demo credit costs $10. The sample agent has a $100 daily budget, a $50
transaction cap, and approval above $25. A fresh agent joins a default team
with a $150 shared budget; later dashboard team edits survive restart.

| Operator command | Action |
| --- | --- |
| `/status`, `/pending` | Inspect balances or pending requests |
| `/approve ID`, `/reject ID` | Approve/execute or reject a request |
| `/resume ID` | Execute a request approved through the dashboard |
| `/kill`, `/unpause` | Stop or re-enable chatbot spending |
| `/help`, `/exit` | Show help or exit |

Command IDs are numeric **request IDs**, distinct from UUID order IDs.
Conversation and approval input mappings are in memory; see
[chatbot instructions](sample_app/CHATBOT.md) for restart recovery.

## Open the dashboard

Use a second terminal with the chatbot's database:

```powershell
.\.venv\Scripts\python.exe -m spendguard.cli --db sample_app\chatbot.db dashboard --env-file sample_app\.env
```

Open [localhost:8501](http://localhost:8501). Review requests, approve or deny
held purchases, inspect model usage and workflow events, edit team budgets,
and manage queued email. After approving a wrapped chatbot purchase, use
`/resume ID` in the chatbot to execute it; dashboard approval alone does not
run the wrapped tool.

Optional `OPENAI_INPUT_USD_PER_MILLION` and `OPENAI_OUTPUT_USD_PER_MILLION`
settings supply trusted model rates. Missing rates or usage remain unknown.
Known estimates reduce later available funds but are not provider invoices.

Configure `SPENDGUARD_SMTP_*` in the ignored `.env`, then use
**Email notifications → Send / retry queued email**. Emails never send
automatically. See [insights and email configuration](docs/insights.md).

## Offline examples

These examples use local simulations and require no model-provider credentials:

```powershell
# Core allow/hold/deny example:
.\.venv\Scripts\python.exe sample_app\main.py
# Scripted LangChain agent:
.\.venv\Scripts\python.exe sample_app\langchain_agent.py
# Seed an isolated dashboard with explicitly synthetic model usage:
.\.venv\Scripts\python.exe sample_app\dashboard_demo.py
.\.venv\Scripts\python.exe -m spendguard.cli --db sample_app\dashboard_demo.db dashboard
```

Each example has its own database. Use `--reset` only on a dedicated demo
database when you intend to clear its history. See
[sample application usage](sample_app/README.md) and [dashboard instructions](docs/dashboard.md).

## Tests and validation

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pip install -r sample_app\requirements-chatbot.txt
.\.venv\Scripts\python.exe -m pytest -q
```

The last full-suite run passed **142 tests**. After automatic UUIDs were added,
all **24 chatbot tests** passed; the full suite was not rerun for that change.
Tests use scripted models, temporary databases, automated Streamlit checks,
and mocked SMTP. Release archives passed strict Twine validation, and a fresh
wheel installation passed core and CLI checks. Checks ran on Python 3.14;
the declared Python 3.10+ range has not been tested across a version matrix.
Live provider/email integration and a manual browser walkthrough remain unverified.

## Repository layout

| Path | Purpose |
| --- | --- |
| `spendguard/` | Policy, SQLite storage, integrations, CLI, and dashboard |
| `sample_app/` | Consumer examples, chatbot, and offline dashboard demo |
| `tests/` | Core, integration, chatbot, and dashboard checks |
| `docs/` | API, integration, dashboard, insights, and publishing guides |
| `package_release/` | Self-contained distributable source snapshot |

Keep runtime files in `package_release/spendguard/` synchronized with
`spendguard/` before building a release. See [package usage](package_release/README.md)
and [PyPI publishing steps](docs/publishing.md).

## Current limitations

SpendGuard is a local prototype without an authentication boundary. Processes
must share a local SQLite database to share state. Unwrapped operations are
outside enforcement. LangChain support covers synchronous `StructuredTool`
tools; native async-only tools and streaming output are not supported.

Model estimates are recorded after responses, without pre-call reservation,
cached-token pricing, or invoice reconciliation. Unknown or uninstrumented
model costs can overstate available funds. Daily accounting follows UTC
creation dates. Kill switches cannot undo an operation already executing;
interrupted operations or email sends require manual reconciliation. SMTP
acceptance does not confirm inbox delivery. Tool arguments/results are stored
in SQLite; keep credentials out of them and protect the database.

## Development record

Built for the DevDay Exchange Community Hackathon in Kochi, 10–11 October 2026.
Event information remains in [RULES.md](RULES.md). See [CHANGELOG.md](CHANGELOG.md)
for changes and validation results, [AI_USAGE.md](AI_USAGE.md) for Codex's
contributions, and [SUBMISSION.md](SUBMISSION.md) for submission details.
