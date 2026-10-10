"""Adapter registry and execution entry point used by SpendGuard."""
from __future__ import annotations

from .base import Adapter
from . import mock
from .mock import MockAdapter


REGISTRY: dict[str, Adapter] = {
    "serpapi.com": MockAdapter(),
    "openai.com": MockAdapter(),
    "aws.amazon.com": MockAdapter(),
}


def register(merchant: str, adapter: Adapter) -> None:
    """Add or replace an adapter using a case-insensitive merchant key."""
    REGISTRY[merchant.lower()] = adapter


def execute(request: dict) -> dict:
    """Execute through a registered adapter; return a failure result on errors."""
    try:
        merchant = request["merchant"].lower()
        adapter = REGISTRY.get(merchant)
        if adapter is None:
            return {"ok": False, "receipt_id": None, "detail": "no adapter registered"}
        result = adapter.execute(request)
        return {
            "ok": bool(result.get("ok", False)),
            "receipt_id": result.get("receipt_id"),
            "detail": str(result.get("detail", "")),
        }
    except Exception as exc:
        return {"ok": False, "receipt_id": None, "detail": str(exc) or "execution failed"}


__all__ = ["Adapter", "MockAdapter", "REGISTRY", "register", "execute", "mock"]
