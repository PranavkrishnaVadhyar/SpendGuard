"""SpendGuard-governed research agent with an offline scripted demo."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from spendguard.tools import governed


def _build_guard():
    from spendguard import SpendGuard

    try:
        from seed_demo import ensure_demo_agent
    except ImportError:
        from examples.seed_demo import ensure_demo_agent

    guard = SpendGuard(db_path=os.getenv("SPENDGUARD_DB", "spendguard.db"))
    ensure_demo_agent(guard)
    return guard


def make_tools(guard: Any, wait_timeout: float = 300):
    @governed(
        guard,
        "research-bot",
        "serpapi.com",
        amount=0.01,
        reason=lambda query: f"search: {query}",
        wait_timeout=wait_timeout,
    )
    def search(query: str) -> str:
        """Return a local page that represents untrusted search content."""
        return Path(__file__).with_name("poisoned_page.txt").read_text(encoding="utf-8")

    @governed(
        guard,
        "research-bot",
        merchant=lambda merchant, amount, reason: merchant,
        amount=lambda merchant, amount, reason: amount,
        reason=lambda merchant, amount, reason: reason,
        wait_timeout=wait_timeout,
    )
    def buy(merchant: str, amount: float, reason: str) -> dict[str, Any]:
        return {"purchased": merchant, "amount": amount, "reason": reason}

    return search, buy


def _show_result(guard: Any, label: str, result: Any) -> None:
    print(f"{label}: {result}")
    if isinstance(result, dict) and result.get("error") == "timeout":
        pending = guard.pending()
        request_id = pending[-1].id if pending else "<id>"
        print(
            f"waiting for approval: run `spendguard approve {request_id}` or use dashboard"
        )


def scripted_demo() -> None:
    guard = _build_guard()
    search, buy = make_tools(guard, wait_timeout=0)
    _show_result(guard, "search", search("best cloud research tools"))
    _show_result(guard, "aws purchase", buy("aws.amazon.com", 40, "compute credits"))
    _show_result(guard, "gift card purchase", buy("giftcard.example", 30, "gift cards"))


def live_demo() -> None:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise SystemExit("Install the OpenAI extra to use the live demo: pip install 'spendguard[openai]'") from exc

    client = OpenAI()
    guard = _build_guard()
    search, buy = make_tools(guard)
    tools = [
        {
            "type": "function",
            "name": "search",
            "description": "Search untrusted research material.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "buy",
            "description": "Request a governed purchase.",
            "parameters": {
                "type": "object",
                "properties": {
                    "merchant": {"type": "string"},
                    "amount": {"type": "number"},
                    "reason": {"type": "string"},
                },
                "required": ["merchant", "amount", "reason"],
                "additionalProperties": False,
            },
        },
    ]
    messages: list[Any] = [
        {"role": "system", "content": "Research safely and use tools for any purchase."},
        {"role": "user", "content": "Research tools and buy only what is approved."},
    ]
    for _ in range(10):
        response = client.responses.create(
            model="gpt-4.1-mini", input=messages, tools=tools
        )
        messages.extend(response.output)
        calls = [item for item in response.output if item.type == "function_call"]
        if not calls:
            print(response.output_text)
            return
        for call in calls:
            arguments = json.loads(call.arguments)
            result = search(**arguments) if call.name == "search" else buy(**arguments)
            _show_result(guard, call.name, result)
            messages.append(
                {
                    "type": "function_call_output",
                    "call_id": call.call_id,
                    "output": json.dumps(result),
                }
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scripted", action="store_true", help="run without OpenAI")
    args = parser.parse_args()
    if args.scripted:
        scripted_demo()
    else:
        live_demo()


if __name__ == "__main__":
    main()
