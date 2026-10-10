from spendguard.adapters import Adapter, execute, register
from spendguard.adapters import mock


def test_allowlisted_merchant_succeeds():
    result = execute({"merchant": "openai.com"})
    assert result["ok"] is True
    assert result["receipt_id"].startswith("rcpt_")


def test_unknown_merchant_is_rejected():
    result = execute({"merchant": "unknown.example"})
    assert result == {"ok": False, "receipt_id": None, "detail": "no adapter registered"}


def test_forced_failure_only_happens_once(monkeypatch):
    monkeypatch.setattr(mock, "FAIL_NEXT", True)
    monkeypatch.delenv("SPENDGUARD_MOCK_FAIL_NEXT", raising=False)
    failed = execute({"merchant": "openai.com"})
    succeeded = execute({"merchant": "openai.com"})
    assert failed["ok"] is False
    assert failed["detail"] == "simulated failure"
    assert succeeded["ok"] is True


def test_malformed_request_never_raises():
    result = execute(None)
    assert result["ok"] is False
    assert result["receipt_id"] is None


def test_register_adds_custom_adapter():
    class CustomAdapter(Adapter):
        def execute(self, request):
            return {"ok": True, "receipt_id": "custom", "detail": "custom adapter"}

    register("CUSTOM.EXAMPLE", CustomAdapter())
    assert execute({"merchant": "custom.example"})["receipt_id"] == "custom"
