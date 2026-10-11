"""Durable model usage, workflow metadata, and budget notifications."""

import math
from uuid import uuid4

from spendguard import budget, db, teams
from spendguard.errors import UnknownAgent, NotFound


def link_request(conn, trace_id, request_id, agent_id, status):
    if trace_id is None:
        return
    trace = conn.execute("SELECT agent_id FROM traces WHERE id=?", (trace_id,)).fetchone()
    if trace is None or trace[0] != agent_id:
        raise ValueError("trace does not belong to this agent")
    cursor = conn.execute("INSERT OR IGNORE INTO request_traces VALUES (?,?)", (request_id, trace_id))
    if cursor.rowcount:
        conn.execute("""INSERT INTO trace_events(trace_id,kind,name,status,request_id,created_at)
            VALUES (?,'request','tool request',?,?,?)""", (trace_id, status, request_id, db.now()))


class Insights:
    def __init__(self, db_path):
        self.db_path = db_path

    def create_team(self, team_id, daily_budget, name=None):
        teams.create(self.db_path, team_id, daily_budget, name)

    def assign_agent(self, agent_id, team_id):
        teams.assign(self.db_path, agent_id, team_id)

    def start_trace(self, agent_id, label="Agent run", session_id=None):
        if not isinstance(label, str) or not label.strip() or len(label) > 200:
            raise ValueError("invalid trace label")
        if session_id is not None and (not isinstance(session_id, str) or len(session_id) > 200):
            raise ValueError("invalid session id")
        trace_id = str(uuid4())
        with db.transaction(self.db_path) as conn:
            if not conn.execute("SELECT 1 FROM agents WHERE id=?", (agent_id,)).fetchone():
                raise UnknownAgent("unknown agent")
            conn.execute("INSERT INTO traces VALUES (?,?,?,?,?,?,NULL)",
                         (trace_id, agent_id, session_id, label, "running", db.now()))
        return trace_id

    def finish_trace(self, trace_id, status="completed"):
        if status not in {"completed", "failed"}:
            raise ValueError("invalid trace status")
        with db.transaction(self.db_path) as conn:
            cursor = conn.execute("UPDATE traces SET status=?,finished_at=? WHERE id=?",
                                  (status, db.now(), trace_id))
            if not cursor.rowcount:
                raise NotFound("unknown trace")

    def event(self, trace_id, kind, name, status):
        if any(not isinstance(v, str) or not v or len(v) > 200 for v in (kind, name, status)):
            raise ValueError("invalid trace event")
        with db.transaction(self.db_path) as conn:
            conn.execute("""INSERT INTO trace_events(trace_id,kind,name,status,created_at)
                VALUES (?,?,?,?,?)""", (trace_id, kind, name, status, db.now()))

    def record_model_usage(self, agent_id, event_key, model, input_tokens=0, output_tokens=0,
                           *, trace_id=None, input_rate=None, output_rate=None, usage_known=True):
        if not isinstance(usage_known, bool):
            raise ValueError("usage_known must be a boolean")
        for value in (input_tokens, output_tokens):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError("token counts must be non-negative integers")
        for value in (input_rate, output_rate):
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                                      or not math.isfinite(value) or value < 0):
                raise ValueError("rates must be finite non-negative USD per million tokens")
        if any(not isinstance(v, str) or not v.strip() or len(v) > 200 for v in (event_key, model)):
            raise ValueError("invalid model usage key or model")
        cost = None
        if usage_known and input_rate is not None and output_rate is not None:
            cost = (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000
            if not math.isfinite(cost):
                raise ValueError("estimated cost is too large")
        with db.transaction(self.db_path) as conn:
            existing = conn.execute("SELECT * FROM model_usage WHERE event_key=?", (event_key,)).fetchone()
            if existing is not None:
                expected = (agent_id, model, input_tokens, output_tokens, int(usage_known), cost, trace_id)
                actual = tuple(existing[key] for key in ('agent_id','model','input_tokens','output_tokens','usage_known','estimated_cost','trace_id'))
                if actual != expected:
                    raise ValueError("usage key belongs to a different model call")
                return
            if not conn.execute("SELECT 1 FROM agents WHERE id=?", (agent_id,)).fetchone():
                raise UnknownAgent("unknown agent")
            if trace_id is not None:
                trace = conn.execute("SELECT agent_id FROM traces WHERE id=?", (trace_id,)).fetchone()
                if trace is None or trace[0] != agent_id:
                    raise ValueError("trace does not belong to this agent")
            member = conn.execute("SELECT team_id FROM team_members WHERE agent_id=?", (agent_id,)).fetchone()
            conn.execute("""INSERT OR IGNORE INTO model_usage VALUES (?,?,?,?,?,?,?,?,?,?)""",
                         (event_key, agent_id, member[0] if member else None, trace_id, model,
                          input_tokens, output_tokens, int(usage_known), cost, db.now()))

    def snapshot(self):
        with db.transaction(self.db_path) as conn:
            timestamp = db.now()
            db.expire(conn, timestamp)
            team_rows = [teams.ledger(conn, row[0], timestamp) for row in conn.execute("SELECT id FROM teams ORDER BY id")]
            agent_rows = [{"id": row[0], **budget.ledger(conn, row[0], timestamp)}
                          for row in conn.execute("SELECT id FROM agents ORDER BY id")]
            for kind, rows in (("agent", agent_rows), ("team", team_rows)):
                for row in rows:
                    if row['daily_budget'] > 0 and row['available'] <= row['daily_budget'] * 0.2:
                        conn.execute("""INSERT OR IGNORE INTO notifications
                            (event_key,message,created_at) VALUES (?,?,?)""",
                            (f"budget:{kind}:{row['id']}:{timestamp[:10]}",
                             f"{kind.title()} {row['id']} has used or reserved at least 80% of its tracked budget.", timestamp))
            usage = [dict(row) for row in conn.execute("SELECT * FROM model_usage ORDER BY created_at DESC,rowid DESC LIMIT 200")]
            traces = [dict(row) for row in conn.execute("SELECT * FROM traces ORDER BY created_at DESC,rowid DESC LIMIT 100")]
            events = [dict(row) for row in conn.execute("SELECT * FROM trace_events ORDER BY id DESC LIMIT 500")]
            notifications = [dict(row) for row in conn.execute("SELECT * FROM notifications ORDER BY id DESC LIMIT 100")]
            members = [dict(row) for row in conn.execute("SELECT * FROM team_members ORDER BY agent_id")]
            totals = dict(conn.execute("""SELECT COUNT(*) AS calls,COALESCE(SUM(input_tokens),0) AS input_tokens,
                COALESCE(SUM(output_tokens),0) AS output_tokens,COALESCE(SUM(estimated_cost),0) AS estimated_cost,
                COALESCE(SUM(estimated_cost IS NULL),0) AS unpriced_calls FROM model_usage
                WHERE substr(created_at,1,10)=?""", (timestamp[:10],)).fetchone())
            by_model = [dict(row) for row in conn.execute("""SELECT model,COUNT(*) AS calls,
                SUM(input_tokens) AS input_tokens,SUM(output_tokens) AS output_tokens,
                SUM(estimated_cost) AS estimated_cost FROM model_usage
                WHERE substr(created_at,1,10)=? GROUP BY model""", (timestamp[:10],))]
            context = [dict(row) for row in conn.execute("""SELECT r.id,t.tool_name,rt.team_id,
                GROUP_CONCAT(x.trace_id) AS trace_ids FROM requests r
                LEFT JOIN tool_calls t ON t.request_id=r.id LEFT JOIN request_teams rt ON rt.request_id=r.id
                LEFT JOIN request_traces x ON x.request_id=r.id GROUP BY r.id ORDER BY r.id DESC LIMIT 50""")]
            return {"teams": team_rows, "members": members, "usage": usage,
                    "traces": traces, "events": events, "notifications": notifications,
                    "usage_totals": totals, "by_model": by_model, "request_context": context}
