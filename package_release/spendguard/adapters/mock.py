"""Deterministic local payment adapter for demos and development."""
from __future__ import annotations

import os
import secrets
import time

from .base import Adapter


FAIL_NEXT = False


class MockAdapter(Adapter):
    def execute(self, request: dict) -> dict:
        global FAIL_NEXT
        time.sleep(0.2)
        failed = FAIL_NEXT or os.getenv("SPENDGUARD_MOCK_FAIL_NEXT") == "1"
        if failed:
            FAIL_NEXT = False
            if os.getenv("SPENDGUARD_MOCK_FAIL_NEXT") == "1":
                os.environ.pop("SPENDGUARD_MOCK_FAIL_NEXT", None)
            return {"ok": False, "receipt_id": None, "detail": "simulated failure"}
        return {
            "ok": True,
            "receipt_id": "rcpt_" + secrets.token_hex(4),
            "detail": "mock payment",
        }
