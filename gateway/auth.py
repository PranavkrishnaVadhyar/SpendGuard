"""Agent token hashing and constant-time administrator authentication."""

import hashlib
import os
import secrets

from fastapi import Header, HTTPException
from gateway import db


def agent_id(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer ") or not authorization[7:].strip():
        raise HTTPException(401, "invalid agent token")
    digest = hashlib.sha256(authorization[7:].encode()).hexdigest()
    with db.connection() as conn:
        row = conn.execute("SELECT id FROM agents WHERE token_hash=?", (digest,)).fetchone()
    if row is None:
        raise HTTPException(401, "invalid agent token")
    return row["id"]


def admin(x_admin_key: str | None = Header(default=None)):
    expected = os.getenv("ADMIN_KEY", "dev-admin-key")
    if x_admin_key is None or not secrets.compare_digest(x_admin_key.encode(), expected.encode()):
        raise HTTPException(403, "invalid admin key")
