"""Validated inputs and public request representation."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator


class SpendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    merchant: str = Field(min_length=1, max_length=2048)
    amount: float = Field(gt=0, allow_inf_nan=False)
    reason: str = Field(max_length=4000)
    idempotency_key: str = Field(min_length=1, max_length=200)

    @field_validator("merchant", "idempotency_key")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


class Approval(BaseModel):
    approve: StrictBool
    approver: str = Field(min_length=1, max_length=200)

    @field_validator("approver")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


class Switch(BaseModel):
    scope: Literal["global", "agent"]
    agent_id: str | None = None


RECORD_FIELDS = (
    "id", "agent_id", "merchant", "amount", "reason", "status",
    "decision_reason", "explanation", "receipt_id", "approver",
    "created_at", "decided_at", "expires_at",
)


def record(row) -> dict:
    return {key: row[key] for key in RECORD_FIELDS}
