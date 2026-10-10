import spendguard.explain as explainer


REQUEST = {"merchant": "openai.com", "amount": 2.5, "reason": "Summarize papers"}


def test_missing_api_key_returns_fallback(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert explainer.explain(REQUEST, 10, 50) == (
        "Agent requests $2.50 from openai.com. Reason given: Summarize papers."
    )


def test_returns_model_text(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(explainer, "_call_llm", lambda messages: "A concise summary.")
    assert explainer.explain(REQUEST, 10, 50) == "A concise summary."


def test_llm_failure_returns_fallback(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def fail(messages):
        raise TimeoutError("timed out")

    monkeypatch.setattr(explainer, "_call_llm", fail)
    assert "Agent requests $2.50" in explainer.explain(REQUEST, 10, 50)


def test_malformed_request_never_raises(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    assert explainer.explain(None, 0, 0).startswith("Agent requests $0.00")


def test_missing_openai_package_returns_fallback(monkeypatch):
    import sys

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setitem(sys.modules, "openai", None)
    assert explainer.explain(REQUEST, 10, 50).startswith("Agent requests $2.50")
