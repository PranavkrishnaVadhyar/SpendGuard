# Model usage, workflows, team budgets, and email

The core keeps these records in the same SQLite file as spending requests.
Construction creates additive tables without deleting existing requests.
The dashboard exposes four tabs: Model usage, Workflows, Team budgets, and
Email notifications. `python -m spendguard.cli --db PATH insights` prints the
same data as JSON. No external tracing service is required.

## Shared team budgets

```python
guard.insights.create_team("research", daily_budget=150, name="Research team")
guard.insights.assign_agent("research-bot", "research")
# Assign another existing agent to share the limit.
guard.insights.assign_agent("analysis-bot", "research")
```

Each agent belongs to at most one team. The dashboard can create/update team
limits and assign registered agents. Both individual and team limits must allow
a purchase. Admission and reservation happen in one SQLite write transaction,
so concurrent agents cannot reserve the same remaining team funds. Pending and
approved requests reserve funds; rejection/expiry/cancellation release them.

Team membership is snapshotted when a request or model-usage record is created.
Reassignment does not move historical spending/reservations to another team.
Pre-existing requests created before team assignment remain unassigned. Limits
use UTC creation dates; changing a limit affects future admissions and does not
revoke existing approvals. Reset preserves agents, policies, teams, and membership.

## Model usage and cost estimates

```python
trace = guard.insights.start_trace("research-bot", label="Research run", session_id="session-1")
guard.insights.record_model_usage(
    "research-bot", "unique-provider-call-id", "your-model", 1000, 200,
    trace_id=trace, input_rate=INPUT_USD_PER_MILLION,
    output_rate=OUTPUT_USD_PER_MILLION,
)
guard.insights.finish_trace(trace)
```

Rates must be supplied by trusted application code; SpendGuard does not guess
current provider prices. The chatbot reads optional
`OPENAI_INPUT_USD_PER_MILLION` and `OPENAI_OUTPUT_USD_PER_MILLION`. Blank pricing
or missing token metadata produces an **unknown cost**, not a zero-cost claim.
For LangChain, `spendguard.integrations.usage.UsageTracker` captures reported
`usage_metadata` (or provider token_usage fallback) through model callbacks.
The chatbot installs this callback on every turn, including intermediate model
calls before/after tools. Failed calls are retained with unknown cost.

Known estimates reduce available individual/team funds for subsequent tool
requests. `spent` remains settled tool spending; `model_estimated_cost` is
separate, and `available` subtracts both plus reservations. Reporting shows
today's complete aggregate and the latest 200 model records. It does not reserve
model cost before generation or guarantee a cap across in-flight model calls.
Cached-token discounts, reasoning/provider billing differences, other fees,
and actual invoice reconciliation are not modeled. Unknown costs can overstate
available funds. Uninstrumented provider calls remain outside tracking.

## Workflow history

The chatbot creates a session ID and a trace for each turn. Model/tool events
record names, status, timestamps, and linked request IDs. Wrapped tools accept
`config.metadata.spendguard_trace_id`; the trace must belong to the same agent.
Later approvals, rejections, execution, expiry, and cancellation append events
to the originating workflow. Retried calls can link to a new workflow without
executing again. A completed turn may still have a pending purchase.

Prompt/response text is not copied into trace metadata. Tool arguments/results
continue to exist in the existing tool-call store. The dashboard shows the most
recent 100 workflows and events from the latest 500 event records. Running
traces left after a crash require manual reconciliation; reset refuses active
traces, executing requests, or notifications currently marked sending.

## Email notifications

Request holds/denials and later state changes create durable outbox records.
Dashboard/insights refresh also creates one 80%-budget warning per entity/day
when known spending plus reservations reach that threshold. Warnings are not
a background scheduler: open/refresh the dashboard or request an insights
snapshot. Messages include request IDs, agent IDs, amount, merchant, and status;
they exclude prompts, tool arguments, provider errors, and SMTP credentials.

Configure these in ignored `sample_app/.env`:

```dotenv
SPENDGUARD_SMTP_HOST=your-smtp-host
SPENDGUARD_SMTP_PORT=587
SPENDGUARD_SMTP_SECURITY=starttls
SPENDGUARD_SMTP_FROM=sender@example.com
SPENDGUARD_SMTP_TO=reviewer@example.com
SPENDGUARD_SMTP_USERNAME=
SPENDGUARD_SMTP_PASSWORD=
```

Use your provider's real configuration; username/password must both be set if
authentication is required. `ssl` is supported for implicit TLS (set its port
explicitly, commonly 465); unencrypted SMTP is not supported. Terminal values
override the file. Start the chatbot and dashboard against the same database:

```powershell
.\.venv\Scripts\python.exe sample_app\chatbot.py
.\.venv\Scripts\python.exe -m spendguard.cli --db sample_app\chatbot.db dashboard --env-file sample_app\.env
```

Open http://localhost:8501 and use **Send / retry queued email**. No email is
sent by refreshing, chatting, or approving. The action attempts at most 20
queued/failed messages with a 10-second SMTP operation timeout. Sending may take
time if several messages fail. `sent` means SMTP acceptance, not confirmed inbox
delivery. Failed rows retain a sanitized error class and attempt count; click
again to retry. Interrupted `sending` rows have an ambiguous outcome and are
not blindly retried. There are no links/buttons in email granting approval;
the trusted local dashboard/CLI records the human decision.

Programmatic delivery is available through `EmailSettings.from_env()` and
`send_pending(guard.db_path, settings)` in `spendguard.notifications`.
Settings/credentials are process-local, not stored in SQLite. Tests mock SMTP
and model responses; no live emails, model calls, or payments were used.

Sources: [LangChain model usage](https://docs.langchain.com/oss/python/langchain/models),
[Python SMTP](https://docs.python.org/3/library/smtplib.html),
[Streamlit application testing](https://docs.streamlit.io/develop/api-reference/app-testing).
