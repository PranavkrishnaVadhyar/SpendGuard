# Interactive LangChain chatbot

`chatbot.py` is a terminal chatbot using LangChain's `create_agent` and an
OpenAI chat model. It retains the conversation during the current process.
Its purchase tool is wrapped by SpendGuard. Purchases simulate buying credits
locally; model API calls use your OpenAI account and may incur charges.
SpendGuard does not track those model costs.

## Setup and launch

From the **SpendGuard repository root**, using the existing environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r sample_app\requirements-chatbot.txt
$env:OPENAI_API_KEY = "your-api-key"
$env:OPENAI_MODEL = "your-tool-calling-model"
.\.venv\Scripts\python.exe sample_app\chatbot.py
```

Replace both placeholders with your configuration. Use a model supporting tool
calling that is available to your account. You can pass `--model MODEL_NAME`
instead of setting `OPENAI_MODEL`. The sample deliberately requires an explicit
model choice. Environment files are not loaded automatically. Keys belong in
the environment, not in the application source. See the official
[OpenAI API setup](https://developers.openai.com/api/docs/quickstart) and
[LangChain ChatOpenAI integration](https://docs.langchain.com/oss/python/integrations/chat/openai).

To use this directory as an independent consumer application, create an
environment inside it and install your supplied SpendGuard source directory:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install "C:\path\to\package_release[langchain]"
.\.venv\Scripts\python.exe -m pip install -r requirements-chatbot.txt
# Set OPENAI_API_KEY and OPENAI_MODEL in this terminal as above.
.\.venv\Scripts\python.exe chatbot.py
```

The default database is `chatbot.db` beside the script, separate from the
other examples. `--db PATH` selects another database. `--reset` explicitly
clears requests and kill state for **all agents in the selected database**;
use only a dedicated sample database. Startup registers the chatbot with the
fixed demonstration policy below while preserving its existing kill state.

## Try the conversation

```text
You: Hello! What can you do?
You: Buy 1 demo credit with order ID order-1.
Tool result: ... "status": "settled" ...

You: Buy 3 demo credits with order ID order-2.
Tool result: ... "status": "pending_approval", "request_id": 2 ...
You: /approve 2
... "status": "settled" ...

You: Buy 8 demo credits with order ID order-3.
Tool result: ... "status": "denied" ...
You: /status
You: /exit
```

Request IDs vary with database history. Read the actual tool output before
typing a command. The terminal displays tool results independently of the
model's natural-language response. The agent receives purchase and read-only
status tools; approval, rejection, kill, and resume are local operator commands.

Each demo credit has a declared cost of $10. The chatbot has a $100 daily UTC
budget, a $50 per-request cap, and approval above $25. Its merchant allowlist
contains `credits.example`. With a fresh database, one credit settles, three
credits wait for approval, and eight credits are denied by the per-request cap.
These are illustrative amounts, not actual debits or a payment-provider connection.

## Commands and approval

| Command | Effect |
| --- | --- |
| `/status` | Show the chatbot's balance and kill state |
| `/pending` | List its requests awaiting approval |
| `/approve ID` | Approve and execute a purchase submitted in this session |
| `/reject ID` | Reject a pending purchase and release its reservation |
| `/resume ID` | Execute a purchase approved through the CLI/dashboard |
| `/kill` | Stop this chatbot's spending and cancel held/approved requests |
| `/unpause` | Re-enable this chatbot's spending |
| `/help` | Show commands and example prompts |
| `/exit` | End the session |

For dashboard approval, install the dashboard extra and start it with this
same absolute database path. From the repository root:

```powershell
.\.venv\Scripts\python.exe -m spendguard.cli --db sample_app\chatbot.db dashboard
```

After dashboard approval, type `/resume ID` in the chatbot. The sample uses
`wait_timeout=0`, so the chat remains available while an order is held.
Approvals expire after 300 seconds if undecided. After approval, reservation
continues until execution or cancellation; there is no automatic worker here.

An order ID identifies one purchase. Retrying with the same order ID and
quantity returns the saved state/result instead of buying again. Changing the
quantity for an existing ID is denied. Use a new ID for a new purchase. After
restarting the chatbot, reissue the same order ID and quantity to restore its
session mapping, then approve/resume if needed. The command rejects approval
when the current session has no saved inputs. Chat history and that mapping
are in memory; spending records, arguments, and results remain in SQLite.

## Validation and limits

Automated tests use scripted local LangChain models and temporary databases,
including the terminal interaction and approval flow. No paid API request is
needed by those tests. Live OpenAI chat quality, account/model availability,
and interactive dashboard behavior require separate verification.

With pytest and the chatbot requirements installed, run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_chatbot.py -q
```

The chatbot's 17 tests passed; the full repository suite passed with 113 tests.

Tools use the existing synchronous StructuredTool integration. Unwrapped
operations and model usage are outside its budget. The local operator/SQLite
interfaces have no authentication. Kill cannot undo an executing operation;
crashes or provider side effects require manual reconciliation. Model failures
show an error rather than invented responses; inspect `/pending` and `/status`
before retrying a purchase with its original order ID. A graph limit bounds
agent tool loops but does not create a model-spending budget. For a production
payment tool, replace the simulated executor with your provider operation and
use provider-side idempotency too.
