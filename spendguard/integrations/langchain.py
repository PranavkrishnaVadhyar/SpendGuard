"""Spend controls around synchronous LangChain tools (also usable with ainvoke)."""

import json
import math
import time

try:
    from langchain_core.runnables import RunnableConfig
    from langchain_core.tools import StructuredTool
except ImportError as exc:
    raise ImportError('Install SpendGuard with the langchain extra: pip install "spendguard[langchain]"') from exc

from spendguard import db
from spendguard.constants import TERMINAL
from spendguard.guard import _outcome


def wrap_tool(tool, guard, *, agent_id, merchant, amount, reason="",
              wait_timeout=300, poll_interval=0.5):
    """Wrap a regular synchronous BaseTool; amount is fixed or a trusted kwargs callback.

    Reuse config.metadata.spendguard_idempotency_key to resume/retry the same
    action. Otherwise every invocation is a new spend request. Results are an
    envelope containing status and the original JSON-compatible tool result.
    """
    if not isinstance(tool, StructuredTool) or not callable(tool.func):
        raise TypeError("wrap_tool requires a synchronous LangChain StructuredTool")
    if tool.args_schema is None or isinstance(tool.args_schema, dict):
        raise ValueError("tool must have a Pydantic input schema")
    # Runtime/state injection needs execution-context persistence, outside v1 scope.
    if tool.get_input_schema().model_json_schema() != tool.tool_call_schema.model_json_schema():
        # Compare properties instead: LangChain changes schema titles for tool calls.
        full = tool.get_input_schema().model_json_schema().get("properties", {})
        public = tool.tool_call_schema.model_json_schema().get("properties", {})
        if full != public:
            raise ValueError("injected runtime/state arguments are not supported")
    for value, positive in ((wait_timeout, False), (poll_interval, True)):
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or value < 0 or (positive and value == 0)):
            raise ValueError("wait_timeout must be non-negative and poll_interval positive")

    def run(config: RunnableConfig, **kwargs):
        # JSON snapshot prevents caller mutation and makes retries compare the action.
        arguments = json.dumps(kwargs, sort_keys=True, ensure_ascii=False, allow_nan=False)
        inputs = json.loads(arguments)
        cost = amount(inputs) if callable(amount) else amount
        key = (config.get("metadata") or {}).get("spendguard_idempotency_key")

        def execute(saved_inputs):
            return tool.invoke(saved_inputs, config=config)

        description = reason or f"Tool {tool.name}: {arguments}"[:4000]
        outcome = guard._request(agent_id, merchant, cost, description, key,
                                 {"name": tool.name, "arguments": arguments,
                                  "trace_id": (config.get("metadata") or {}).get("spendguard_trace_id")}, execute)
        deadline = time.monotonic() + wait_timeout
        while outcome.request_id is not None:
            record = guard.get(outcome.request_id)
            if record.status in {"allowed", "approved"}:
                outcome = _outcome(guard._execute_request(record.id, execute))
                continue
            outcome = _outcome(record.to_dict())
            remaining = deadline - time.monotonic()
            if record.status in TERMINAL or remaining <= 0:
                break
            time.sleep(min(poll_interval, remaining))
        result = None
        if outcome.status == "settled":
            with db.connection(guard.db_path) as conn:
                saved = conn.execute("SELECT result FROM tool_calls WHERE request_id=?",
                                     (outcome.request_id,)).fetchone()
            result = json.loads(saved["result"])
        return {"decision": outcome.decision, "status": outcome.status, "reason": outcome.reason,
                "request_id": outcome.request_id, "receipt_id": outcome.receipt_id, "result": result}

    # StructuredTool supplies ainvoke through LangChain's worker-thread fallback.
    return StructuredTool.from_function(
        func=run, name=tool.name, description=tool.description,
        args_schema=tool.args_schema, infer_schema=False, return_direct=tool.return_direct,
    )
