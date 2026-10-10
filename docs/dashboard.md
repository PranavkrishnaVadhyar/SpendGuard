# SpendGuard dashboard and CLI

The dashboard and CLI read and update the same local SQLite database through the public `SpendGuard` API. The dashboard is an optional dependency and can show fixture data before the core package is available.

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
spendguard approve ID [--approver NAME]
spendguard reject ID [--approver NAME]
spendguard kill [--agent ID]
spendguard resume [--agent ID]
spendguard dashboard [--db PATH] [--port 8501]
```

The dashboard approves and rejects requests as `dashboard`. Its kill switch, per-agent kill, resume, and reset controls operate on the selected database. The CLI and dashboard display request descriptions and budget information; they never display credentials.

## Optional explainer and mock adapter

The default adapter is a local mock for `serpapi.com`, `openai.com`, and `aws.amazon.com`. Set `SPENDGUARD_MOCK_FAIL_NEXT=1` to simulate a one-time payment failure. Custom adapters can be added with `spendguard.adapters.register(merchant, adapter)`.

The explainer uses `OPENAI_API_KEY` and optional `OPENAI_MODEL` (`gpt-4o-mini` by default). OpenAI is imported only when a summary is requested. Without the key, package, or a successful API call, it returns a plain template. Explanation text is for approvers and never participates in policy decisions.
