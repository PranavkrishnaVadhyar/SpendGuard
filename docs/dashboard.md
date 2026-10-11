# SpendGuard dashboard and CLI

The dashboard and CLI read and update the same local SQLite database through the public `SpendGuard` API. The dashboard is an optional dependency; fixture mode displays explicit sample data with controls disabled. Database read failures stop rendering budgets/controls instead of reporting a healthy empty inbox.

## Install and run

From the repository root, install the package with its dashboard extra:

```powershell
pip install -e ".[dashboard]"
spendguard dashboard
```

To view the sample feed without opening the database, set the fixture switch:

```powershell
$env:DASHBOARD_FIXTURE = "1"
spendguard dashboard
```

The dashboard refreshes every two seconds. In fixture mode its approval and control buttons are disabled.

## Database and commands

`SPENDGUARD_DB` selects the SQLite file and defaults to `spendguard.db`. The global `--db PATH` option overrides it. The dashboard command also accepts `--db PATH` and `--port PORT`.

```text
spendguard status
spendguard feed [--limit N]
spendguard pending
spendguard insights
spendguard approve ID [--approver NAME]
spendguard reject ID [--approver NAME]
spendguard kill [--agent ID]
spendguard resume [--agent ID]
spendguard dashboard [--db PATH] [--port 8501] [--env-file PATH]
```

The dashboard approves and rejects requests as `dashboard`. Its kill switch, per-agent kill/resume, and reset controls operate on the selected database. Reset also clears model usage, workflows, and notifications, retaining team configuration. It refuses active execution, running workflows, and in-flight email sends. The CLI and dashboard display request descriptions and budget information; they never display SMTP credentials. For LangChain tools, approval authorizes the request; the original wrapper must execute/resume it.

## New dashboard tabs

- **Model usage:** today's reported input/output tokens, known cost estimates, unknown-cost warnings, per-model breakdown, and recent call records.
- **Workflows:** sessions/turns, model/tool events, request links, and later approval/execution transitions. No prompt/response content is copied into trace metadata.
- **Team budgets:** shared available/reserved/spent balances, known model estimates, member assignments, and forms to create/update limits and assign agents.
- **Email notifications:** durable state-change/80%-budget alerts, attempt counts, sanitized failures, and an explicit Send / retry action. Email is never sent automatically on refresh.

See [insights configuration](insights.md) for USD pricing, team semantics, SMTP settings, unknown costs, and delivery limitations. SMTP credentials may be loaded with `--env-file sample_app/.env`; terminal variables override the file.

An isolated offline demo exercises shared team limits, model estimates, workflow events, approval, denial, and notifications without network calls:

```powershell
.\.venv\Scripts\python.exe sample_app\dashboard_demo.py --reset
.\.venv\Scripts\python.exe -m spendguard.cli --db sample_app\dashboard_demo.db dashboard
```

The demo labels its model usage as synthetic and its purchases as simulated. It uses a separate database and never sends email. Automated Streamlit tests verify tab rendering and denial controls; a live browser walkthrough remains unverified.

## Optional explainer and mock adapter

The default adapter is a local mock for `serpapi.com`, `openai.com`, and `aws.amazon.com`. Set `SPENDGUARD_MOCK_FAIL_NEXT=1` to simulate a one-time payment failure. Custom adapters can be added with `spendguard.adapters.register(merchant, adapter)`.

The explainer uses `OPENAI_API_KEY` and optional `OPENAI_MODEL` (`gpt-4o-mini` by default). OpenAI is imported only when a summary is requested. Without the key, package, or a successful API call, it returns a plain template. Explanation text is for approvers and never participates in policy decisions.
