import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

pytest.importorskip("langchain")
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool

from spendguard import Policy, SpendGuard, db
from spendguard.integrations.langchain import wrap_tool


@pytest.fixture
def setup(tmp_path):
    calls = []

    @tool
    def buy(quantity: int) -> dict:
        """Buy local demo credits."""
        calls.append(quantity)
        return {"quantity": quantity}

    guard = SpendGuard(tmp_path / "tools.db", explainer=lambda *args: None)
    guard.create_agent("bot", Policy(100, 50, 25, ["credits.example"]))
    wrapped = wrap_tool(buy, guard, agent_id="bot", merchant="credits.example",
                        amount=lambda args: args["quantity"] * 10, wait_timeout=0)
    return guard, buy, wrapped, calls


def config(key):
    return {"metadata": {"spendguard_idempotency_key": key}}


def test_allow_result_schema_and_replay(setup):
    guard, original, wrapped, calls = setup
    assert wrapped.args_schema == original.args_schema
    result = wrapped.invoke({"quantity": 1}, config("same"))
    assert result["status"] == "settled" and result["result"] == {"quantity": 1}
    assert wrapped.invoke({"quantity": 1}, config("same")) == result
    assert calls == [1]
    assert guard.status()["agents"][0]["spent"] == 10


def test_changed_arguments_and_plain_request_cannot_reuse_tool_key(setup):
    guard, _, wrapped, calls = setup
    wrapped.invoke({"quantity": 1}, config("same"))
    assert wrapped.invoke({"quantity": 2}, config("same"))["status"] == "denied"
    assert guard.request("bot", "credits.example", 10, idempotency_key="same").status == "denied"
    assert calls == [1]


def test_plain_key_cannot_become_tool_call(setup):
    guard, _, wrapped, calls = setup
    guard.executor = lambda req: {"ok": True}
    guard.request("bot", "credits.example", 10, idempotency_key="same")
    assert wrapped.invoke({"quantity": 1}, config("same"))["status"] == "denied"
    assert calls == []


@pytest.mark.parametrize("operation,status", [("reject", "rejected"), ("kill", "cancelled"),
                                              ("expire", "expired")])
def test_hold_never_executes_without_approval(setup, operation, status):
    guard, _, wrapped, calls = setup
    held = wrapped.invoke({"quantity": 3}, config("held"))
    assert held["status"] == "pending_approval" and calls == []
    if operation == "kill":
        guard.kill()
    elif operation == "expire":
        with db.transaction(guard.db_path) as conn:
            conn.execute("UPDATE requests SET expires_at='2000-01-01T00:00:00Z'")
    else:
        guard.reject(held["request_id"])
    assert wrapped.invoke({"quantity": 3}, config("held"))["status"] == status
    assert calls == []
    assert guard.status()["agents"][0]["reserved"] == 0


def test_external_approval_waits_for_original_tool_then_replays(setup):
    guard, _, wrapped, calls = setup
    held = wrapped.invoke({"quantity": 3}, config("held"))
    ui = SpendGuard(guard.db_path, executor=lambda req: pytest.fail("UI must not execute mock"))
    assert ui.approve(held["request_id"]).status == "approved"
    assert calls == []
    assert guard.status()["agents"][0]["reserved"] == 30
    result = wrapped.invoke({"quantity": 3}, config("held"))
    assert result["status"] == "settled" and result["result"] == {"quantity": 3}
    assert wrapped.invoke({"quantity": 3}, config("held")) == result
    assert calls == [3]


def test_waiting_wrapper_observes_external_approval(setup):
    guard, original, _, calls = setup
    held_event = Event()
    guard.on_hold = lambda record: held_event.set()
    wrapped = wrap_tool(original, guard, agent_id="bot", merchant="credits.example",
                        amount=30, wait_timeout=3, poll_interval=0.01)
    with ThreadPoolExecutor() as pool:
        future = pool.submit(wrapped.invoke, {"quantity": 3}, config("held"))
        assert held_event.wait(2)
        SpendGuard(guard.db_path).approve(guard.pending()[0].id)
        assert future.result(timeout=4)["status"] == "settled"
    assert calls == [3]


def test_denial_prevents_action(setup):
    _, _, wrapped, calls = setup
    assert wrapped.invoke({"quantity": 99})["status"] == "denied"
    assert calls == []


def test_concurrent_replays_execute_once(setup):
    _, _, wrapped, calls = setup
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: wrapped.invoke({"quantity": 1}, config("one")), range(8)))
    assert calls == [1]
    assert {r["request_id"] for r in results} == {results[0]["request_id"]}
    assert all(r["status"] in {"settled", "executing"} for r in results)


def test_tool_failure_releases_budget(setup):
    guard, _, _, _ = setup

    @tool
    def fail(quantity: int) -> str:
        """Fail before purchase."""
        raise RuntimeError("private provider error")

    wrapped = wrap_tool(fail, guard, agent_id="bot", merchant="credits.example", amount=10)
    assert wrapped.invoke({"quantity": 1})["status"] == "failed"
    assert guard.status()["agents"][0]["available"] == 100


def test_ainvoke_and_tool_message(setup):
    _, _, wrapped, calls = setup
    result = asyncio.run(wrapped.ainvoke({"quantity": 1}))
    assert result["status"] == "settled" and calls == [1]
    message = wrapped.invoke({"name": "buy", "args": {"quantity": 1},
                              "id": "call-2", "type": "tool_call"})
    assert message.tool_call_id == "call-2"


class ScriptedModel(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


def test_create_agent_executes_wrapped_tool(setup):
    _, _, wrapped, calls = setup
    model = ScriptedModel(responses=[
        AIMessage(content="", tool_calls=[{"name": "buy", "args": {"quantity": 1}, "id": "call-1"}]),
        AIMessage(content="Done"),
    ])
    agent = create_agent(model=model, tools=[wrapped])
    result = agent.invoke({"messages": [HumanMessage(content="Buy one credit")]})
    assert result["messages"][-1].content == "Done"
    assert calls == [1]


def test_reset_removes_tool_arguments(setup):
    guard, _, wrapped, _ = setup
    wrapped.invoke({"quantity": 1})
    guard.reset()
    with db.connection(guard.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM tool_calls").fetchone()[0] == 0


def test_concurrent_different_inputs_keep_their_arguments(setup):
    guard, _, wrapped, calls = setup
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda q: wrapped.invoke({"quantity": q}), [1, 2]))
    assert sorted(calls) == [1, 2]
    assert [r["result"]["quantity"] for r in results] == [1, 2]
    assert guard.status()["agents"][0]["spent"] == 30


def test_kill_after_approval_prevents_tool_execution(setup):
    guard, _, wrapped, calls = setup
    held = wrapped.invoke({"quantity": 3}, config("held"))
    SpendGuard(guard.db_path).approve(held["request_id"])
    guard.kill("bot")
    assert wrapped.invoke({"quantity": 3}, config("held"))["status"] == "cancelled"
    assert calls == []


def test_async_only_tool_rejected_at_wrapping(setup):
    guard, _, _, _ = setup

    @tool
    async def async_buy(quantity: int) -> str:
        """Async-only purchase."""
        return "done"

    with pytest.raises(TypeError, match="synchronous"):
        wrap_tool(async_buy, guard, agent_id="bot", merchant="credits.example", amount=10)
