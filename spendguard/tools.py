"""Function decorators that route side effects through :class:`SpendGuard`."""

from __future__ import annotations

import functools
import hashlib
import inspect
import json
import threading
from typing import Any, Callable

try:  # Import the library error when the Person A core is present.
    from .errors import RequestDenied
except ImportError:  # Keeps this module importable while the core is being integrated.
    class RequestDenied(RuntimeError):
        """Fallback used only before the core error types are available."""

        def __init__(self, outcome: Any) -> None:
            self.outcome = outcome
            super().__init__(getattr(outcome, "reason", "Request denied"))


def _value(value: Any, args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    return value(*args, **kwargs) if callable(value) else value


def _idempotency_key(
    agent_id: str,
    merchant: Any,
    amount: Any,
    reason: Any,
    call_number: int,
) -> str:
    payload = json.dumps(
        {
            "agent_id": agent_id,
            "merchant": merchant,
            "amount": amount,
            "reason": reason,
            "call_number": call_number,
        },
        default=str,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _denial(outcome: Any) -> dict[str, Any]:
    return {"error": "denied", "reason": getattr(outcome, "reason", None)}


def governed(
    guard: Any,
    agent_id: str,
    merchant: str | Callable[..., str],
    amount: float | Callable[..., float] | None = None,
    reason: str | Callable[..., str] | None = None,
    wait_timeout: float = 300,
    raise_on_deny: bool = False,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorate a side-effecting function with a fail-closed SpendGuard check.

    ``merchant`` is also allowed to be callable so examples can govern a tool
    whose destination is supplied by the model at call time.
    """

    def decorate(function: Callable[..., Any]) -> Callable[..., Any]:
        signature = inspect.signature(function)
        sequence = 0
        sequence_lock = threading.Lock()

        @functools.wraps(function)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            nonlocal sequence
            call_kwargs = dict(kwargs)
            requested_key = call_kwargs.pop("_idempotency_key", None)

            try:
                resolved_merchant = _value(merchant, args, call_kwargs)
                if amount is None:
                    bound = signature.bind(*args, **call_kwargs)
                    bound.apply_defaults()
                    resolved_amount = bound.arguments["amount"]
                else:
                    resolved_amount = _value(amount, args, call_kwargs)
                resolved_reason = (
                    function.__name__ if reason is None else _value(reason, args, call_kwargs)
                )
                with sequence_lock:
                    sequence += 1
                    call_number = sequence
                idempotency_key = requested_key or _idempotency_key(
                    agent_id,
                    resolved_merchant,
                    resolved_amount,
                    resolved_reason,
                    call_number,
                )
                outcome = guard.request(
                    agent_id,
                    resolved_merchant,
                    resolved_amount,
                    resolved_reason,
                    idempotency_key,
                )
            except Exception:
                return {"error": "guard_unavailable"}

            if getattr(outcome, "settled", False):
                result = function(*args, **call_kwargs)
                return result if result is not None else {
                    "ok": True,
                    "receipt_id": getattr(outcome, "receipt_id", None),
                }

            if getattr(outcome, "decision", None) == "deny":
                if raise_on_deny:
                    raise RequestDenied(outcome)
                return _denial(outcome)

            if getattr(outcome, "decision", None) == "hold":
                try:
                    record = guard.wait(outcome.request_id, timeout=wait_timeout)
                except Exception:
                    return {"error": "guard_unavailable"}
                if getattr(record, "status", None) == "settled":
                    result = function(*args, **call_kwargs)
                    return result if result is not None else {
                        "ok": True,
                        "receipt_id": getattr(record, "receipt_id", None),
                    }
                status = getattr(record, "status", None)
                error = "timeout" if status not in {
                    "failed",
                    "denied",
                    "rejected",
                    "expired",
                    "cancelled",
                } else status
                return {
                    "error": error,
                    "reason": getattr(record, "decision_reason", None),
                }

            if (
                getattr(outcome, "decision", None) == "failed"
                or getattr(outcome, "status", None) == "failed"
            ):
                return {"error": "failed", "reason": getattr(outcome, "reason", None)}
            return {"error": "guard_unavailable"}

        return wrapped

    return decorate
