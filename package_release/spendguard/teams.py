"""Shared daily budgets; request and usage membership is snapshotted at creation."""

from decimal import Decimal
import math

from spendguard import db
from spendguard.constants import RESERVING
from spendguard.errors import UnknownAgent, NotFound


def ledger(conn, team_id, timestamp):
    row = conn.execute("SELECT * FROM teams WHERE id=?", (team_id,)).fetchone()
    if row is None:
        raise NotFound("unknown team")
    requests = conn.execute("""SELECT r.amount,r.status FROM requests r JOIN request_teams t
        ON t.request_id=r.id WHERE t.team_id=? AND substr(r.created_at,1,10)=?""",
        (team_id, timestamp[:10])).fetchall()
    spent = sum((Decimal(str(r['amount'])) for r in requests if r['status'] == 'settled'), Decimal(0))
    reserved = sum((Decimal(str(r['amount'])) for r in requests if r['status'] in RESERVING), Decimal(0))
    usage = conn.execute("""SELECT estimated_cost FROM model_usage
        WHERE team_id=? AND substr(created_at,1,10)=?""", (team_id, timestamp[:10])).fetchall()
    model_cost = sum((Decimal(str(r[0])) for r in usage if r[0] is not None), Decimal(0))
    return {**dict(row), "spent": float(spent), "reserved": float(reserved),
            "model_estimated_cost": float(model_cost), "unpriced_calls": sum(r[0] is None for r in usage),
            "available": float(Decimal(str(row['daily_budget'])) - spent - reserved - model_cost)}


def create(db_path, team_id, daily_budget, name=None):
    if not isinstance(team_id, str) or not team_id.strip() or len(team_id) > 200:
        raise ValueError("invalid team id")
    if name is not None and (not isinstance(name, str) or not name.strip() or len(name) > 200):
        raise ValueError("invalid team name")
    if (isinstance(daily_budget, bool) or not isinstance(daily_budget, (int, float))
            or not math.isfinite(daily_budget) or daily_budget < 0):
        raise ValueError("team budget must be finite and non-negative")
    with db.transaction(db_path) as conn:
        conn.execute("""INSERT INTO teams VALUES (?,?,?) ON CONFLICT(id) DO UPDATE
            SET name=excluded.name,daily_budget=excluded.daily_budget""", (team_id, name or team_id, daily_budget))


def assign(db_path, agent_id, team_id):
    with db.transaction(db_path) as conn:
        if not conn.execute("SELECT 1 FROM agents WHERE id=?", (agent_id,)).fetchone():
            raise UnknownAgent("unknown agent")
        if not conn.execute("SELECT 1 FROM teams WHERE id=?", (team_id,)).fetchone():
            raise NotFound("unknown team")
        conn.execute("INSERT OR REPLACE INTO team_members VALUES (?,?)", (agent_id, team_id))
