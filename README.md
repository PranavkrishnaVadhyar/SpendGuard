# SpendGuard

SpendGuard is a local-first Python library that gives autonomous agents a
policy boundary before they spend. It keeps the decision, approval record, and
receipt alongside the application in SQLite instead of putting payment
credentials or direct egress in the agent's hands.

## Install

```bash
pip install spendguard
pip install "spendguard[dashboard]"
pip install "spendguard[openai]"
```

For a checkout of the library, install the development extras and run the
deterministic tests:

```bash
pip install -e ".[dev]"
pytest tests/test_tools.py tests/test_attacks.py -q
```

## Quickstart

```python
from spendguard import Policy, SpendGuard
from spendguard.tools import governed

guard = SpendGuard(db_path="spendguard.db")
guard.create_agent("research", Policy(10, 5, 5, ["openai.com"]))

@governed(guard, "research", "openai.com", amount=2, reason="research")
def buy():
    return "purchased"

print(buy())
```

An allowed request settles before `buy` runs. A request over the budget or for
a merchant outside the allowlist returns a structured denial and the wrapped
function never runs. Requests at or above the approval threshold wait for a
human decision; approve them from the dashboard, the `spendguard approve`
command, or your application code.

## Main calls

| Call | Purpose |
| --- | --- |
| `SpendGuard(db_path=...)` | Opens the local SQLite policy store. |
| `create_agent(id, policy)` | Registers an agent and its spending policy. |
| `request(...)` | Records an allow, hold, or denial without raising. |
| `approve(id)` / `reject(id)` | Resolves an approval hold. |
| `governed(...)` | Wraps a side-effecting tool with a fail-closed check. |
| `kill()` / `resume()` | Stops or resumes spending immediately. |

Use a real execution adapter only after a request has settled. Adapter details
and the policy model live in `docs/core.md`; dashboard setup lives in
`docs/dashboard.md`.

## Demos

```bash
python examples/seed_demo.py
python examples/openai_agent.py --scripted
python examples/attacks.py
```

The scripted demo never imports OpenAI. The attack suite creates temporary
SQLite databases, writes its actual result table to `docs/results.md`, and
returns a non-zero exit code if any scenario fails. Before relying on those
results, run it against the installed core; the checked-in table starts as an
explicit not-run disclosure.

## Payment model and assumptions

SpendGuard authorizes and records a decision; it is not a payment processor.
Your executor must make settlement idempotent, secure its provider credentials,
and reconcile provider results with SpendGuard receipts. SQLite is a good fit
for local demos and small deployments; use appropriate operational controls
when sharing a database across processes or hosts.

## Roadmap

- Slack approval notifications
- Stripe execution adapter
- anomaly detection
- tamper-evident audit hashes
- SSO and role-based approvals
- payment reconciliation workflows
- network enforcement for untrusted agents
