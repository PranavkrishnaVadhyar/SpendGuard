"""A real LangChain agent graph using a scripted local model and a guarded tool."""

from pathlib import Path

from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import tool

from spendguard import Policy, SpendGuard
from spendguard.integrations.langchain import wrap_tool


@tool
def buy_credits(quantity: int) -> dict:
    """Purchase demo credits locally. No external service or money is involved."""
    print(f"Demo tool executed: {quantity} credit(s)")
    return {"credits": quantity}


class ScriptedModel(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


def main():
    guard = SpendGuard(Path(__file__).with_name("langchain.db"), explainer=lambda *args: None)
    guard.create_agent("langchain-bot", Policy(100, 50, 25, ["credits.example"]))
    guarded_buy = wrap_tool(buy_credits, guard, agent_id="langchain-bot",
                            merchant="credits.example", amount=lambda args: args["quantity"] * 10)
    model = ScriptedModel(responses=[
        AIMessage(content="", tool_calls=[{"name": "buy_credits", "args": {"quantity": 1}, "id": "demo-1"}]),
        AIMessage(content="Demo complete; see the tool result for the SpendGuard decision."),
    ])
    agent = create_agent(model=model, tools=[guarded_buy])
    result = agent.invoke({"messages": [{"role": "user", "content": "Buy one demo credit"}]})
    for message in result["messages"]:
        print(message.type, message.content)


if __name__ == "__main__":
    main()
