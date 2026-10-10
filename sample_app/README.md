# Standalone consumer application

This directory demonstrates using the installed `spendguard` package from a
small Python application owned by a package user. This directory can be copied
outside the SpendGuard repository. It imports the public API directly, without
changing Python's import path or copying package code. Python 3.10+ is required.

```text
my-agent-app/
    main.py       # Your application; imports the installed spendguard package
    .venv/        # Your application's environment
    sample.db     # Your application's local state, created when run
```

## Setup

Open PowerShell **inside this sample directory** and create a separate environment:

```powershell
python -m venv .venv
```

During local development, while this directory is still inside the repository,
install SpendGuard from its parent directory as a normal package:

```powershell
.\.venv\Scripts\python.exe -m pip install "..[dashboard]"
```

If you copied this sample to a separate project, replace the path below with the
location of a SpendGuard source checkout containing `pyproject.toml`:

```powershell
.\.venv\Scripts\python.exe -m pip install "C:\path\to\SpendGuard[dashboard]"
```

Once a release of **this project** is published to the intended package index,
users can instead install `spendguard` (core only) or `spendguard[dashboard]` by
name. Publication has not been performed or verified in this session; the local
checkout installation above is the currently documented source for this project.
The package's source folder does not need to live alongside the user's app.

## Run the sample

```powershell
.\.venv\Scripts\python.exe main.py --reset
```

The script creates `sample.db` beside `main.py`, registers Sample Research Bot with a
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
.\.venv\Scripts\spendguard.exe --db sample.db dashboard
```

Open http://localhost:8501. In another PowerShell window inside this sample directory:

```powershell
.\.venv\Scripts\python.exe main.py --reset --wait
```

Click **Approve** or **Deny** for the $30 request. The script polls the database
for up to two minutes and prints the resulting state. Approval changes the
balance to $40 spent, $0 reserved, $10 available; rejection leaves $10 spent,
$0 reserved, $40 available. The hold expires after 30 minutes if undecided.
Stopping the wait does not cancel a pending request. Stop the dashboard with Ctrl+C.

CLI commands can inspect the same sample:

```powershell
.\.venv\Scripts\spendguard.exe --db sample.db status
.\.venv\Scripts\spendguard.exe --db sample.db pending
.\.venv\Scripts\spendguard.exe --db sample.db feed
```

## What to reuse

`Policy` defines limits and the merchant allowlist. `create_agent()` registers or
updates the agent. `request()` performs enforcement and returns an `Outcome`;
inspect its decision/status rather than assuming success. `wait()` retrieves a
held request's final state after human intervention. `status()` reports balances.
For independent purchases, use a unique business idempotency key for each one.

The central integration looks like this in the user's own Python code:

```python
from spendguard import SpendGuard, Policy

guard = SpendGuard("my-agent.db")
guard.create_agent("my-agent", Policy(50, 100, 25, ["openai.com"]))
outcome = guard.request("my-agent", "openai.com", 10,
                        reason="Research credits", idempotency_key="order-1")
print(outcome.status, outcome.receipt_id)
```

`request()` already invokes the configured adapter for allowed spending. A real
integration must supply an adapter/executor that performs the paid operation;
the built-in adapters only simulate it. Do not run the same purchase again after
`request()` reports settlement. Automated `governed` tool wrappers are not yet
part of this checkout. An executor registered only in one process is not shared
with a separate dashboard process; the sample deliberately uses default mocks.

This sample uses only the package and Python standard library. Dashboard use
requires the package's optional Streamlit extra. Standalone installation, sample
execution, and interactive approval have not yet been verified; see the repository
validation log.
