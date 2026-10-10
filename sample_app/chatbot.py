"""Interactive LangChain chatbot with SpendGuard-controlled demo purchases."""

import argparse
import json
import os
from pathlib import Path
import re
from typing import Annotated

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from pydantic import Field

from spendguard import Policy, SpendGuard, SpendGuardError
from spendguard.integrations.langchain import wrap_tool

AGENT_ID = "chatbot"
DEFAULT_DB = Path(__file__).with_name("chatbot.db")
DEFAULT_ENV_FILE = Path(__file__).with_name(".env")
OrderId = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,80}$")]
Quantity = Annotated[int, Field(strict=True, ge=1)]
HELP = """Commands (typed directly by the operator):
  /status       Show budget and kill state
  /pending      List requests awaiting approval
  /approve ID   Approve and execute a purchase from this session
  /reject ID    Reject a pending purchase
  /resume ID    Execute a purchase approved in another interface
  /kill         Stop this chatbot's spending
  /unpause      Re-enable this chatbot's spending
  /help         Show commands
  /exit         Exit
Try: Buy 1 demo credit with order ID order-1.
Try: Buy 3 demo credits with order ID order-2.
Try: Buy 8 demo credits with order ID order-3.
"""
SYSTEM_PROMPT = """You are a helpful chatbot demonstrating SpendGuard spending controls.
Chat normally and use tools when appropriate. Demo credits cost $10 each.
Only call buy_demo_credits when the user explicitly requests a purchase and
provides an order ID; ask for an ID if missing. Reuse that ID for retries of the
same purchase. Never change an ID or split a purchase to bypass a denial.
Read the tool result: only settled means executed. Pending means waiting for
human approval, not purchased. Tell the user the request ID and /approve ID or
/reject ID commands for held calls. You cannot approve, reject, reset, or change
limits. Do not claim that real money was spent: purchases are local simulations.
Use spending_status for current balances. Model API costs are separate and
are not tracked by SpendGuard. Never invent purchase success or a receipt.
"""


class Chatbot:
    def __init__(self, guard, model):
        self.guard = guard
        self.messages = []
        self.orders = {}

        @tool
        def execute_demo_purchase(order_id: OrderId, quantity: Quantity) -> dict:
            """Execute a local demo credit purchase. No money or external service is involved."""
            return {"order_id": order_id, "credits": quantity, "simulated": True}

        self.purchase = wrap_tool(
            execute_demo_purchase, guard, agent_id=AGENT_ID, merchant="credits.example",
            amount=lambda args: args["quantity"] * 10, wait_timeout=0,
        )

        @tool
        def buy_demo_credits(order_id: OrderId, quantity: Quantity) -> dict:
            """Request demo credits at $10 each. User must supply a unique order ID;
            reuse it for retries. Pending purchases need operator approval.
            """
            return self.submit_purchase(order_id, quantity)

        @tool
        def spending_status() -> dict:
            """Read the chatbot's current daily budget, spending, reservations, and kill state."""
            return self.status()

        self.agent = create_agent(model=model, tools=[buy_demo_credits, spending_status],
                                  system_prompt=SYSTEM_PROMPT)

    def submit_purchase(self, order_id, quantity):
        # Business IDs are per purchase, rather than shared across an agent run.
        if not isinstance(order_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", order_id):
            raise ValueError("order ID must contain 1-80 letters, numbers, underscores, or hyphens")
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
            raise ValueError("quantity must be a positive integer")
        inputs = {"order_id": order_id, "quantity": quantity}
        result = self.purchase.invoke(inputs, config={
            "metadata": {"spendguard_idempotency_key": f"chatbot:{order_id}"},
        })
        if result["request_id"] is not None:
            self.orders[result["request_id"]] = inputs
        return result

    def status(self):
        status = self.guard.status()
        return {"kill_global": status["kill_global"],
                "agent": next(agent for agent in status["agents"] if agent["id"] == AGENT_ID)}

    def chat(self, text):
        if not text.strip():
            return []
        previous_count = len(self.messages)
        result = self.agent.invoke(
            {"messages": self.messages + [HumanMessage(content=text)]},
            config={"recursion_limit": 12},
        )
        self.messages = result["messages"]
        return self.messages[previous_count + 1:]

    def command(self, text):
        parts = text.split()
        command = parts[0]
        if command in {"/approve", "/reject", "/resume"}:
            if len(parts) != 2 or not parts[1].isdigit() or int(parts[1]) < 1:
                raise ValueError(f"Usage: {command} REQUEST_ID")
            request_id = int(parts[1])
            record = self.guard.get(request_id)
            if record.agent_id != AGENT_ID:
                raise ValueError("request belongs to another agent")
            if command == "/reject":
                result = self.guard.reject(request_id, approver="chatbot-operator").to_dict()
            else:
                if request_id not in self.orders:
                    raise ValueError("Reissue the purchase with its original order ID and quantity first; this session has no saved inputs")
                if command == "/approve":
                    self.guard.approve(request_id, approver="chatbot-operator")
                elif record.status != "approved":
                    raise ValueError("request must be approved before /resume")
                result = self.submit_purchase(**self.orders[request_id])
        elif len(parts) != 1:
            raise ValueError("This command takes no arguments; use /help")
        elif command == "/status":
            result = self.status()
        elif command == "/pending":
            result = [record.to_dict() for record in self.guard.pending() if record.agent_id == AGENT_ID]
        elif command in {"/kill", "/unpause"}:
            action = self.guard.kill if command == "/kill" else self.guard.resume
            action(AGENT_ID)
            result = self.status()
        elif command == "/help":
            return HELP
        else:
            raise ValueError("Unknown command; use /help")
        # Keep subsequent natural-language answers aware of operator decisions.
        self.messages.append(HumanMessage(content=f"Local operator {text} returned: {json.dumps(result)}"))
        return result


def make_guard(db_path):
    guard = SpendGuard(db_path, explainer=lambda *args: None)
    guard.create_agent(AGENT_ID, Policy(100, 50, 25, ["credits.example"]), "Sample Chatbot")
    return guard


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--model", help="Override OPENAI_MODEL")
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE,
                        help="Configuration file (default: .env beside chatbot.py)")
    parser.add_argument("--reset", action="store_true", help="Clear requests and kill state in the selected database")
    args = parser.parse_args(argv)
    try:
        from dotenv import load_dotenv

        load_dotenv(args.env_file, override=False, interpolate=False, encoding="utf-8-sig")
    except ImportError:
        print("Install python-dotenv using the chatbot requirements file.")
        return 1
    except (OSError, UnicodeError):
        print("Could not read the environment file. Check its path, permissions, and UTF-8 encoding.")
        return 1
    args.model = args.model or os.environ.get("OPENAI_MODEL")
    if not os.environ.get("OPENAI_API_KEY", "").strip():
        print("Set OPENAI_API_KEY in the chatbot .env file or this terminal.")
        return 1
    if not args.model or not args.model.strip():
        print("Set OPENAI_MODEL or pass --model with a tool-calling model available to your account.")
        return 1
    try:
        from langchain_openai import ChatOpenAI

        model = ChatOpenAI(model=args.model, timeout=30, max_retries=0)
        guard = make_guard(args.db)
        if args.reset:
            guard.reset()
        chatbot = Chatbot(guard, model)
    except ImportError:
        print("Install the chatbot dependencies: python -m pip install -r sample_app/requirements-chatbot.txt")
        return 1
    except Exception as exc:
        print(f"Could not initialize chatbot ({type(exc).__name__}). Check model configuration and database access.")
        return 1
    print(f"SpendGuard chatbot | model: {args.model} | database: {guard.db_path}")
    print("Demo purchases are simulated. Chat model API calls can incur charges and are not budgeted here.")
    print(HELP)
    while True:
        try:
            text = input("You: ").strip()
            if text == "/exit":
                break
            if not text:
                continue
            if text.startswith("/"):
                result = chatbot.command(text)
                print(result if isinstance(result, str) else json.dumps(result, indent=2))
                continue
            for message in chatbot.chat(text):
                if message.type == "tool":
                    print(f"Tool result: {message.content}")
                elif message.type == "ai" and message.content:
                    print(f"Bot: {message.content}")
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye. Purchase records remain in the database.")
            break
        except (ValueError, SpendGuardError) as exc:
            print(f"Error: {exc}")
        except Exception as exc:
            print(f"Chat failed ({type(exc).__name__}). Check credentials/model/network; use /pending and /status before retrying an order with its original ID.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
