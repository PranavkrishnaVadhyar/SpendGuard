# Sample application

This directory demonstrates using the installed `spendguard` package from a
small Python application. It imports the public API directly, without changing
Python's import path or copying package code. Python 3.10+ is required.

## Setup

Run these commands from the repository root (`SpendGuard`), not this directory.
The existing project virtual environment already has the dependencies installed.
For a fresh checkout:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dashboard]"
```

## Run the sample

```powershell
.\.venv\Scripts\python.exe sample_app\main.py --reset
```

The script creates `sample_app/sample.db`, registers Sample Research Bot with a
$50 daily budget and approval above $25, and submits these requests:

| Request | Expected result after reset | Budget effect |
| --- | --- | --- |
| $10 at openai.com | allow / settled | $10 spent |
| $30 at aws.amazon.com | hold / pending_approval | $30 reserved |
| $99 at openai.com | deny / denied | No additional spending |

The resulting balance is $10 spent, $30 reserved, and $10 available. Default
adapters return mock receipts; no actual purchase takes place. The supplied
explanation function is local, so this sample needs no API key or network call.
Explanation runs in a daemon thread and may be interrupted when the script exits.

`--reset` clears requests and kill state in this sample database only, while
preserving agents and policies. Omit it to keep history. Fixed idempotency keys
make repeated runs return the original records without making new purchases;
their statuses may differ after approval, rejection, or expiry.

## Approve through the dashboard

In one PowerShell window, start the dashboard with the same database:

```powershell
.\.venv\Scripts\spendguard.exe --db sample_app\sample.db dashboard
```

Open http://localhost:8501. In another PowerShell window at the repository root:

```powershell
.\.venv\Scripts\python.exe sample_app\main.py --reset --wait
```

Click **Approve** or **Deny** for the $30 request. The script polls the database
for up to two minutes and prints the resulting state. Approval changes the
balance to $40 spent, $0 reserved, $10 available; rejection leaves $10 spent,
$0 reserved, $40 available. The hold expires after 30 minutes if undecided.
Stopping the wait does not cancel a pending request. Stop the dashboard with Ctrl+C.

CLI commands can inspect the same sample:

```powershell
.\.venv\Scripts\spendguard.exe --db sample_app\sample.db status
.\.venv\Scripts\spendguard.exe --db sample_app\sample.db pending
.\.venv\Scripts\spendguard.exe --db sample_app\sample.db feed
```

## What to reuse

`Policy` defines limits and the merchant allowlist. `create_agent()` registers or
updates the agent. `request()` performs enforcement and returns an `Outcome`;
inspect its decision/status rather than assuming success. `wait()` retrieves a
held request's final state after human intervention. `status()` reports balances.
For independent purchases, use a unique business idempotency key for each one.

This sample uses only the package and Python standard library. Dashboard use
requires the package's optional Streamlit extra. Sample execution and interactive
approval have not yet been verified; see the repository validation log.
