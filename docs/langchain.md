# LangChain agents

Install the optional integration from the repository root:

```powershell
python -m pip install -e ".[langchain]"
```

For the standalone `package_release` directory, install `".[langchain]"` from
that directory. SpendGuard has not been published to a package index.

Wrap each paid tool, then pass the returned tool to LangChain's `create_agent`:

```python
from langchain.agents import create_agent
from langchain_core.tools import tool
from spendguard import SpendGuard, Policy
from spendguard.integrations.langchain import wrap_tool

@tool
def buy_credits(quantity: int) -> dict:
    """Buy demo credits locally."""
    return {"credits": quantity}  # Replace with your actual provider operation.

guard = SpendGuard("agent.db", explainer=lambda *args: None)
guard.create_agent("research-bot", Policy(100, 50, 25, ["credits.example"]))
safe_buy = wrap_tool(
    buy_credits, guard, agent_id="research-bot", merchant="credits.example",
    amount=lambda args: args["quantity"] * 10, wait_timeout=120,
)

# With a configured LangChain chat model that supports tool calling:
# agent = create_agent(model=your_model, tools=[safe_buy])
# agent.invoke({"messages": [{"role": "user", "content": "Buy one credit"}]})
```

The merchant and cost calculation belong to trusted application code. Use the
wrapper instead of exposing the original paid tool to the agent. The wrapper
preserves its name, description, and Pydantic argument schema. It returns a
dictionary with `decision`, `status`, `reason`, `request_id`, `receipt_id`, and
`result`. `result` is the original output only after settlement; JSON-compatible
outputs retain their shape, and other values fall back to strings.

An allowed call reserves its declared cost and executes the actual tool, then
settles the request. A denied call never invokes the tool. A held call stores its
arguments and reserves funds while awaiting a human decision. By default the
approval reason includes the tool name and arguments (up to 4,000 characters);
provide `reason=` to choose the text shown to reviewers. Full arguments and
results are stored in the local SQLite database; avoid credentials in inputs.

## Approval and retries

Open the same database in the dashboard with the dashboard extra installed:

```powershell
python -m spendguard.cli --db agent.db dashboard
```

Alternatively use `python -m spendguard.cli --db agent.db approve REQUEST_ID`.
For wrapped tool calls these interfaces record approval without invoking a
default payment adapter. The waiting wrapper sees approval and claims execution
under SQLite's write lock. Rejection, expiry, or kill prevents execution.

`wait_timeout` defaults to 300 seconds; `poll_interval` defaults to 0.5 seconds.
`wait_timeout=0` returns the current state immediately. If waiting ends before
approval, resume by invoking the same wrapper with the same arguments and
business idempotency key. Each new invocation otherwise creates a new request:

```python
config = {"metadata": {"spendguard_idempotency_key": "order-123"}}
result = safe_buy.invoke({"quantity": 3}, config=config)
# After a trusted reviewer approves, if the first call timed out:
result = safe_buy.invoke({"quantity": 3}, config=config)
```

Use a distinct key per paid action. Do not put a single shared key on an entire
multi-tool agent run. Reusing a key for different arguments, tool name, merchant,
or amount fails closed. Settled retries return the saved result without another
execution. Recreate the same wrapper and guard/database after a restart to
resume an approved call using its original key. An approved request remains
reserved until the wrapper resumes or a kill cancels it; approval alone does
not schedule a background worker.

## Offline example

From the repository root after installing the LangChain extra:

```powershell
python sample_app/langchain_agent.py
```

This uses a real `create_agent` graph with a scripted local chat model and a
local demo tool. It needs no API key and spends no money. Its separate database
is `sample_app/langchain.db`; repeated runs are separate purchases and eventually
reach the configured daily budget. For real models, install/configure the model
provider's LangChain package separately.

## Scope

This first integration supports synchronous `StructuredTool` tools, including
ordinary functions decorated with `@tool`, with Pydantic input schemas.
`ainvoke` runs the synchronous wrapper in LangChain's worker thread. Native
async-only tools, injected tool runtime/state arguments, streaming tool output,
and custom `BaseTool` subclasses are outside this version's supported scope.
Only wrapped tool operations are accounted for; LLM inference costs and direct
provider calls outside the wrapper are not intercepted. Costs are declared
before execution, without actual-usage reconciliation or currency conversion.

The local claim prevents concurrent retries from executing the same stored
request again. A process crash or provider error after an external side effect
still needs manual reconciliation; this is not a distributed payment guarantee.
Kill cannot undo an executing operation. Keep real provider idempotency keys in
your paid implementation too. The SQLite file and approval UI are trusted local
interfaces without authentication. Ordinary custom-executor requests still
require executor configuration in their approving process.

The integration uses the official [LangChain tools API](https://docs.langchain.com/oss/python/langchain/tools)
and [agents API](https://docs.langchain.com/oss/python/langchain/agents).
The core remains standard-library-only; LangChain 1.x is an optional dependency.
