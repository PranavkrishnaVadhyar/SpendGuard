"""Standard-library public data models."""

from dataclasses import asdict, dataclass


@dataclass
class Policy:
    daily_budget: float
    per_txn_cap: float
    approval_threshold: float
    allowlist: list[str]


@dataclass
class RequestRecord:
    id: int
    agent_id: str
    merchant: str
    amount: float
    reason: str | None
    status: str
    decision_reason: str | None
    explanation: str | None
    receipt_id: str | None
    approver: str | None
    created_at: str
    decided_at: str | None
    expires_at: str | None
    idempotency_key: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "RequestRecord":
        return cls(**dict(d))


@dataclass
class Outcome:
    decision: str
    status: str
    reason: str
    request_id: int | None
    receipt_id: str | None
    record: RequestRecord | None

    @property
    def settled(self) -> bool:
        return self.status == "settled"
