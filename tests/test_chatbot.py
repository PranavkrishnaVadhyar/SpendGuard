import json

import pytest

pytest.importorskip("langchain")
pytest.importorskip("dotenv")
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, ToolMessage

from sample_app.chatbot import Chatbot, main, make_guard
import sample_app.chatbot as chatbot_module


@pytest.fixture(autouse=True)
def isolate_environment_file(tmp_path, monkeypatch):
    # Never load a developer's actual credentials during tests.
    monkeypatch.setattr(chatbot_module, "DEFAULT_ENV_FILE", tmp_path / ".env")
    monkeypatch.delenv("PYTHON_DOTENV_DISABLED", raising=False)


class ScriptedModel(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):
        assert {tool.name for tool in tools} == {"buy_demo_credits", "spending_status"}
        return self


@pytest.fixture
def bot(tmp_path):
    return Chatbot(make_guard(tmp_path / "chat.db"), ScriptedModel(responses=[
        AIMessage(content="Hello"), AIMessage(content="Hello again"),
    ]))


def test_multi_turn_chat_keeps_context(bot):
    assert bot.chat("My name is Alex")[-1].content == "Hello"
    bot.chat("What is my name?")
    assert [m.content for m in bot.messages] == ["My name is Alex", "Hello", "What is my name?", "Hello again"]


@pytest.mark.parametrize("quantity,status", [(1, "settled"), (3, "pending_approval"), (8, "denied")])
def test_agent_purchase_tool(bot, quantity, status):
    bot.agent = Chatbot(bot.guard, ScriptedModel(responses=[
        AIMessage(content="", tool_calls=[{"name": "buy_demo_credits", "args": {
            "order_id": "order-1", "quantity": quantity}, "id": "call-1"}]),
        AIMessage(content="Check tool result"),
    ])).agent
    messages = bot.chat("Buy demo credits with order ID order-1")
    result = json.loads(next(m.content for m in messages if isinstance(m, ToolMessage)))
    assert result["status"] == status
    assert (result["result"] is not None) == (status == "settled")


def test_operator_approval_and_retry_only_spends_once(bot):
    held = bot.submit_purchase("order-2", 3)
    assert held["status"] == "pending_approval"
    assert bot.status()["agent"]["reserved"] == 30
    result = bot.command(f"/approve {held['request_id']}")
    assert result["status"] == "settled"
    assert bot.submit_purchase("order-2", 3) == result
    assert bot.status()["agent"]["spent"] == 30
    assert bot.submit_purchase("order-2", 4)["status"] == "denied"


def test_reject_and_kill(bot):
    held = bot.submit_purchase("held", 3)
    assert bot.command(f"/reject {held['request_id']}")["status"] == "rejected"
    assert bot.status()["agent"]["reserved"] == 0
    bot.command("/kill")
    assert bot.submit_purchase("blocked", 1)["status"] == "denied"
    bot.command("/unpause")
    assert bot.submit_purchase("new-order", 1)["status"] == "settled"


def test_resume_external_approval(bot):
    held = bot.submit_purchase("held", 3)
    make_guard(bot.guard.db_path).approve(held["request_id"])
    assert bot.command(f"/resume {held['request_id']}")["status"] == "settled"


def test_restart_reissues_original_order_without_duplicate(bot):
    held = bot.submit_purchase("held", 3)
    restarted = Chatbot(make_guard(bot.guard.db_path), ScriptedModel(responses=[AIMessage(content="Hi")]))
    with pytest.raises(ValueError, match="original order"):
        restarted.command(f"/approve {held['request_id']}")
    assert restarted.submit_purchase("held", 3)["request_id"] == held["request_id"]
    assert restarted.command(f"/approve {held['request_id']}")["status"] == "settled"
    assert restarted.submit_purchase("held", 3)["result"]["credits"] == 3


@pytest.mark.parametrize("command", ["/approve", "/approve -1", "/approve abc", "/status extra", "/unknown"])
def test_bad_commands(bot, command):
    with pytest.raises(ValueError):
        bot.command(command)


def test_missing_key_does_not_create_database(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    database = tmp_path / "missing.db"
    assert main(["--db", str(database)]) == 1
    assert "OPENAI_API_KEY" in capsys.readouterr().out
    assert not database.exists()


def test_missing_model_does_not_create_database(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("OPENAI_API_KEY", "not-a-real-key")
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    database = tmp_path / "missing.db"
    assert main(["--db", str(database)]) == 1
    assert "OPENAI_MODEL" in capsys.readouterr().out
    assert not database.exists()


def test_terminal_chat_and_operator_approval(tmp_path, monkeypatch, capsys):
    provider = pytest.importorskip("langchain_openai")
    model = ScriptedModel(responses=[
        AIMessage(content="", tool_calls=[{"name": "buy_demo_credits", "args": {
            "order_id": "terminal-order", "quantity": 3}, "id": "terminal-call"}]),
        AIMessage(content="Waiting for operator approval"),
    ])
    monkeypatch.setattr(provider, "ChatOpenAI", lambda **kwargs: model)
    monkeypatch.setenv("OPENAI_API_KEY", "not-a-real-key")
    prompts = iter(["Buy 3 demo credits with order ID terminal-order", "/approve 1", "/status", "/exit"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(prompts))
    database = tmp_path / "terminal.db"
    assert main(["--db", str(database), "--model", "test-model"]) == 0
    output = capsys.readouterr().out
    assert "pending_approval" in output and '"status": "settled"' in output
    assert make_guard(database).status()["agents"][0]["spent"] == 30


def test_model_error_is_visible_without_dumping_credentials(tmp_path, monkeypatch, capsys):
    provider = pytest.importorskip("langchain_openai")
    monkeypatch.setattr(provider, "ChatOpenAI", lambda **kwargs: ScriptedModel(responses=[AIMessage(content="Hi")]))
    monkeypatch.setenv("OPENAI_API_KEY", "not-a-real-key")

    def fail_chat(self, text):
        raise RuntimeError("private-provider-detail")

    monkeypatch.setattr(Chatbot, "chat", fail_chat)
    prompts = iter(["Hello", "/exit"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(prompts))
    assert main(["--db", str(tmp_path / "failure.db"), "--model", "test-model"]) == 0
    output = capsys.readouterr().out
    assert "Chat failed (RuntimeError)" in output
    assert "private-provider-detail" not in output and "not-a-real-key" not in output


@pytest.mark.parametrize("source", ["default", "custom"])
def test_env_file_loads_without_terminal_variables(tmp_path, monkeypatch, capsys, source):
    provider = pytest.importorskip("langchain_openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    env_file = tmp_path / (".env" if source == "default" else "custom.env")
    env_file.write_text('OPENAI_API_KEY="fake-file-key"\nOPENAI_MODEL="file-model"\n', encoding="utf-8")
    selected = []

    def local_model(**kwargs):
        assert chatbot_module.os.environ["OPENAI_API_KEY"] == "fake-file-key"
        selected.append(kwargs["model"])
        return ScriptedModel(responses=[AIMessage(content="Hi")])

    monkeypatch.setattr(provider, "ChatOpenAI", local_model)
    monkeypatch.setattr("builtins.input", lambda prompt: "/exit")
    arguments = ["--db", str(tmp_path / "from-env.db")]
    if source == "custom":
        arguments += ["--env-file", str(env_file)]
    try:
        assert main(arguments) == 0
        assert selected == ["file-model"]
        assert "fake-file-key" not in capsys.readouterr().out
    finally:
        # dotenv writes to os.environ directly, so clean its additions explicitly.
        chatbot_module.os.environ.pop("OPENAI_API_KEY", None)
        chatbot_module.os.environ.pop("OPENAI_MODEL", None)


@pytest.mark.parametrize("cli_model,expected", [(None, "terminal-model"), ("cli-model", "cli-model")])
def test_terminal_and_cli_override_env_file(tmp_path, monkeypatch, cli_model, expected):
    provider = pytest.importorskip("langchain_openai")
    (tmp_path / ".env").write_text("OPENAI_API_KEY=file-key\nOPENAI_MODEL=file-model\n", encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "terminal-key")
    monkeypatch.setenv("OPENAI_MODEL", "terminal-model")
    selected = []

    def local_model(**kwargs):
        assert chatbot_module.os.environ["OPENAI_API_KEY"] == "terminal-key"
        selected.append(kwargs["model"])
        return ScriptedModel(responses=[AIMessage(content="Hi")])

    monkeypatch.setattr(provider, "ChatOpenAI", local_model)
    monkeypatch.setattr("builtins.input", lambda prompt: "/exit")
    arguments = ["--db", str(tmp_path / "override.db")]
    if cli_model:
        arguments += ["--model", cli_model]
    assert main(arguments) == 0
    assert selected == [expected]
