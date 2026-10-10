"""Pure, ordered policy evaluation. All state is provided by the caller."""

from dataclasses import dataclass
import math
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Decision:
    decision: str
    reason: str


def normalize_merchant(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    try:
        parsed = urlsplit(value.strip() if "://" in value else "//" + value.strip())
        if parsed.scheme and parsed.scheme.lower() not in {"http", "https"}:
            return ""
        if parsed.username is not None or parsed.password is not None:
            return ""
        host = (parsed.hostname or "").lower()
        return host[4:] if host.startswith("www.") else host
    except ValueError:
        return ""


def evaluate(*, global_kill: bool, agent_status: str, amount: float,
             merchant: str, allowlist: list[str], per_txn_cap: float,
             available: float, approval_threshold: float) -> Decision:
    if global_kill:
        return Decision("deny", "kill switch active (global)")
    if agent_status != "active":
        return Decision("deny", "agent disabled or killed")
    if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not math.isfinite(amount) or amount <= 0:
        return Decision("deny", "invalid amount")
    host = normalize_merchant(merchant)
    if not host or host not in {normalize_merchant(item) for item in allowlist}:
        return Decision("deny", "merchant not allowed")
    if amount > per_txn_cap:
        return Decision("deny", "exceeds per-transaction cap")
    if amount > available:
        return Decision("deny", "exceeds remaining budget")
    if amount > approval_threshold:
        return Decision("hold", "needs human approval")
    return Decision("allow", "within policy")
