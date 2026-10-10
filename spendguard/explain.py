"""Optional human-readable summaries for held payment requests."""
from __future__ import annotations

import os


SYSTEM_MESSAGE = (
    "You summarize payment requests for a human approver. Two sentences. "
    "State merchant, amount, stated purpose, and budget context. "
    "Do not recommend approving or denying."
)


def _call_llm(messages: list[dict]) -> str:
    """Call OpenAI lazily so the SpendGuard library has no hard dependency."""
    from openai import OpenAI

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), timeout=5.0)
    response = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        messages=messages,
        max_tokens=150,
        temperature=0.2,
        timeout=5.0,
    )
    return response.choices[0].message.content or ""


def _fallback(request: dict) -> str:
    try:
        amount = float(request.get("amount", 0))
    except (TypeError, ValueError):
        amount = 0.0
    merchant = str(request.get("merchant", "unknown merchant"))
    reason = str(request.get("reason", "No reason provided"))
    return f"Agent requests ${amount:.2f} from {merchant}. Reason given: {reason}."


def explain(request: dict, spent_today: float, daily_budget: float) -> str:
    """Return a short approver summary, falling back if anything fails."""
    fallback = _fallback(request if isinstance(request, dict) else {})
    if not os.getenv("OPENAI_API_KEY"):
        return fallback
    try:
        user_message = (
            f"Merchant: {request.get('merchant', 'unknown merchant')}\n"
            f"Amount: ${float(request.get('amount', 0)):.2f}\n"
            f"Reason: {request.get('reason', 'No reason provided')}\n"
            f"Spent today: ${float(spent_today):.2f}\n"
            f"Daily budget: ${float(daily_budget):.2f}"
        )
        text = _call_llm([
            {"role": "system", "content": SYSTEM_MESSAGE},
            {"role": "user", "content": user_message},
        ])
        return text.strip() or fallback
    except Exception:
        return fallback
