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
Optional LangChain tools: `python -m pip install ".[langchain]"`.
All extras: `python -m pip install ".[all]"`.

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

### LangChain agents

```python
from langchain_core.tools import tool
from spendguard.integrations.langchain import wrap_tool

@tool
def buy_credits(quantity: int) -> dict:
    """Buy local demo credits."""
    return {"credits": quantity}  # Your actual provider operation belongs here.

guard.create_agent("langchain-bot", Policy(100, 50, 25, ["credits.example"]))
safe_buy = wrap_tool(buy_credits, guard, agent_id="langchain-bot",
                    merchant="credits.example", amount=lambda args: args["quantity"] * 10,
                    wait_timeout=120)
# Pass safe_buy in tools=[safe_buy] to langchain.agents.create_agent(model=your_model, ...).
result = safe_buy.invoke({"quantity": 1})
print(result["status"], result["result"])
```

The trusted application sets the merchant and cost calculation. Allowed calls
execute the actual wrapped tool and save its output. Denied calls never execute.
Held calls reserve funds, save arguments, and wait for human approval. The
CLI/dashboard only records approval for wrapped calls; the waiting wrapper
executes them. If waiting times out, retry the same wrapper/arguments with
`config={"metadata": {"spendguard_idempotency_key": "unique-order-id"}}` supplied
on both invocations. Each invocation without a key creates a new spend request.
Reusing a key with different arguments, name, merchant, or cost denies the call;
settled retries return the saved result. Approved requests remain reserved until
the wrapper resumes or kill cancels them. No background worker is scheduled.

The result envelope has decision/status/reason/request_id/receipt_id/result.
JSON-compatible outputs retain their shape; other values fall back to strings.
Tool arguments/results are stored in SQLite. The default approval reason includes
the tool name and arguments (truncated at 4,000 characters); set `reason=` to
customize it. Protect the database and avoid credentials in tool inputs.

Supported: synchronous LangChain `StructuredTool` tools created with `@tool` and
Pydantic schemas; `ainvoke` uses a worker thread. Native async-only tools,
injected runtime/state, custom BaseTool subclasses, and streaming output are
outside this version. Tool costs are declared upfront; model usage can be
recorded through the optional UsageTracker callback described below. Unwrapped
operations remain outside tracking. Install your model provider's package separately.
See the official [LangChain tools documentation](https://docs.langchain.com/oss/python/langchain/tools).

### Core callbacks

`SpendGuard(db_path, executor=callback, explainer=callback, on_hold=callback)`
accepts optional integrations. Executors receive a dict containing
`id, agent_id, merchant, amount, reason, idempotency_key` and return
`{"ok": bool, "receipt_id": str | None, "detail": str}`. Explainers receive
`(request_dict, spent_today, daily_budget)` and return text. Explanation and
hold notification callbacks run in daemon threads; errors are ignored and their
output never controls policy decisions.

Optional OpenAI explanations use process environment variables `OPENAI_API_KEY`
and `OPENAI_MODEL` (default `gpt-4o-mini`). Without a key, SDK, or successful call,
the explainer returns a local template. Environment files are not loaded by the
core automatically; dashboard startup accepts `--env-file PATH` with the dashboard
extra installed. CLI/dashboard database selection uses `SPENDGUARD_DB` or `--db`;
Python callers pass the path to the constructor.

SpendGuard is a trusted local library, without an authentication boundary.
Processes must share the same local database to share state. For ordinary requests, custom executors
and adapter registrations are process-local and must be configured in any
process performing approvals; the stock dashboard/CLI uses default adapters.
Kill cannot undo an action already executing. Interrupted execution may require
manual reconciliation. Daily accounting follows UTC request creation dates.
Constructing a guard preserves data, but incompatible older database schemas
require a separate database file. This is a prototype; a passing test suite
does not validate real-payment integration or an interactive deployment.

## Model usage, workflows, teams, and email

The dashboard has Model usage, Workflows, Team budgets, and Email notifications
tabs. Database reads fail visibly instead of showing healthy empty state. Teams
can be created/updated and agents assigned through its forms. Individual/team
tool reservations share a transaction, preventing concurrent team overspending.
Membership is snapshotted per request/usage; old records are not reassigned.

```python
guard.insights.create_team("research", 150)
guard.insights.assign_agent("research-bot", "research")
trace = guard.insights.start_trace("research-bot", "Research run", session_id="session-1")
# Use a stable unique provider-call ID. Supply trusted USD/million-token rates.
guard.insights.record_model_usage("research-bot", "model-call-1", "your-model",
                                 1000, 200, trace_id=trace,
                                 input_rate=YOUR_INPUT_RATE, output_rate=YOUR_OUTPUT_RATE)
guard.insights.finish_trace(trace)
snapshot = guard.insights.snapshot()
```

Optional LangChain `UsageTracker` from `spendguard.integrations.usage` installs
as an invocation callback and records reported tokens plus model/tool events.
Construct it with `(guard.insights, agent_id, trace_id, model_name, input_rate,
output_rate)` and pass `callbacks=[tracker]` in the invoke config. Set
`metadata.spendguard_trace_id` to link wrapped
tool requests to the same trace. Model/tool names, statuses, and request IDs
are recorded without copying prompt/response text. Existing tool arguments and
results still reside in SQLite.

Known model estimates reduce future available funds alongside settled tool
spending and reservations. Missing usage/pricing stays unknown, not zero.
Estimation is after-response accounting without pre-call reservations or an
in-flight model cap; cached-token discounts, other fees, and invoice
reconciliation are not modeled. Uninstrumented calls are not tracked.
`python -m spendguard.cli --db my-agent.db insights` prints the reporting data.

Notifications queue durably for request changes and, on dashboard/report
refresh, once-per-day 80% budget warnings. They never send automatically.
Configure `SPENDGUARD_SMTP_HOST`, `SPENDGUARD_SMTP_PORT` (default 587),
`SPENDGUARD_SMTP_SECURITY` (`starttls` or `ssl`), `SPENDGUARD_SMTP_FROM`,
`SPENDGUARD_SMTP_TO`, and optional `SPENDGUARD_SMTP_USERNAME`/`SPENDGUARD_SMTP_PASSWORD`
in an ignored environment file. Start the dashboard with:

```powershell
python -m spendguard.cli --db my-agent.db dashboard --env-file .env
```

Click **Send / retry queued email** to attempt queued/failed messages. SMTP
acceptance is recorded as sent; inbox delivery is not confirmed. Failures retain
only an error class; interrupted sending rows need reconciliation before retry.
Credentials are process-local and never stored in the outbox. Programmatic
delivery uses `EmailSettings.from_env()` and `send_pending(guard.db_path, settings)`
from `spendguard.notifications`. Reset clears usage/traces/outbox while retaining
team configuration; active workflows or sends block reset. Tests use local models
and mocked SMTP; no live payment/email integration is claimed.

## Build a distribution

This directory is self-contained. To create wheel and source archives:

```powershell
python -m pip install build
python -m build
```

Artifacts appear in `dist/`. The installation name is `[project].name` in
`pyproject.toml`; the Python import remains `spendguard` unless its source and
imports are renamed. Publishing to a package index is a separate step.
