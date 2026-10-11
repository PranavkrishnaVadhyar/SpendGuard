"""SpendGuard dashboard backed by the local SpendGuard SQLite store."""
from __future__ import annotations

import html
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
FIXTURE_PATH = ROOT / "fixtures" / "feed.json"
GREEN = {"allowed", "settled"}
AMBER = {"pending_approval", "approved", "executing"}
RED = {"denied", "rejected", "cancelled", "failed", "expired"}


def _relative(value: str | None) -> str:
    if not value:
        return "—"
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        seconds = max(0, int((datetime.now(timezone.utc) - moment).total_seconds()))
        if seconds < 60:
            return f"{seconds}s ago"
        if seconds < 3600:
            return f"{seconds // 60}m ago"
        return f"{seconds // 3600}h ago"
    except (TypeError, ValueError):
        return str(value)


def _countdown(value: str | None) -> str:
    if not value:
        return "No expiry set"
    try:
        expiry = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        seconds = int((expiry - datetime.now(timezone.utc)).total_seconds())
        return "Expired" if seconds <= 0 else f"{seconds // 60}m {seconds % 60}s remaining"
    except (TypeError, ValueError):
        return "Expiry unavailable"


def _fixture_data() -> tuple[dict, list[dict]]:
    with FIXTURE_PATH.open(encoding="utf-8") as file:
        feed = json.load(file)
    pending = [item for item in feed.get("requests", []) if item.get("status") == "pending_approval"]
    return feed, pending


def _load_data(st, sg) -> tuple[dict, list[dict], bool]:
    if os.getenv("DASHBOARD_FIXTURE") == "1":
        feed, pending = _fixture_data()
        return feed, pending, True
    try:
        status = sg.status()
        requests = [record.to_dict() for record in sg.feed(50)]
        pending = [record.to_dict() for record in sg.pending()]
        return {**status, "requests": requests, "insights": sg.insights.snapshot()}, pending, False
    except Exception as exc:
        st.error(f"Could not read SpendGuard state ({type(exc).__name__}). Check database access; controls are unavailable.")
        return None, [], False


def _action(st, fn) -> bool:
    try:
        fn()
        st.success("Action completed")
        return True
    except Exception as exc:
        try:
            from spendguard import InvalidState, NotFound
            if isinstance(exc, NotFound):
                st.warning(f"Request or agent not found: {exc}")
                return False
            if isinstance(exc, InvalidState):
                st.warning(f"Request is no longer pending: {exc}")
                return False
        except ImportError:
            pass
        st.warning(f"SpendGuard action failed: {exc}")
        return False


def render_dashboard(st, sg) -> None:
    st.markdown("""<style>
      .big-amount {font-size:1.55rem;font-weight:750}
      .status-green {color:#16803c;font-weight:700}
      .status-amber {color:#b77900;font-weight:700}
      .status-red {color:#c62828;font-weight:700}
      div[data-testid="stMetricValue"] {font-size:2rem}
    </style>""", unsafe_allow_html=True)
    feed, pending, fixture_mode = _load_data(st, sg)
    if feed is None:
        return
    agents = feed.get("agents", [])
    requests = feed.get("requests", [])

    title, kill_col, count_col = st.columns([5, 1.5, 1.5])
    with title:
        st.title("🛡️ SpendGuard")
        if fixture_mode:
            st.caption("Fixture demo data")
    with kill_col:
        st.markdown(f"### {'🔴 KILLED' if feed.get('kill_global', False) else '🟢 OK'}")
    with count_col:
        st.metric("Pending approvals", len(pending))

    st.subheader("Budgets")
    if not agents:
        st.info("No agents are registered yet.")
    for agent in agents:
        daily = max(0.0, float(agent.get("daily_budget", 0) or 0))
        spent = max(0.0, float(agent.get("spent", 0) or 0))
        reserved = max(0.0, float(agent.get("reserved", 0) or 0))
        model_cost = float(agent.get("model_estimated_cost", 0) or 0)
        left = float(agent.get("available", daily - spent - reserved - model_cost))
        with st.container(border=True):
            st.markdown(f"**{agent.get('name', agent.get('id', 'Agent'))}** · {agent.get('status', 'unknown')}")
            st.progress(min(1.0, (spent + reserved + model_cost) / daily) if daily else 0.0)
            st.caption(f"Tool spending ${spent:.2f} · Reserved ${reserved:.2f} · Model estimate ${model_cost:.6f} · Available ${left:.2f} of ${daily:.2f}")
            if agent.get("unpriced_calls", 0):
                st.warning(f"{agent['unpriced_calls']} model calls have unknown cost; available funds may be overstated.")

    _render_insights(st, sg, feed.get("insights", {}), fixture_mode)

    st.subheader("Live feed")
    if requests:
        keys = ("Time", "Agent", "Merchant", "Amount", "Status", "Reason")
        body = []
        for item in requests:
            status = str(item.get("status", "unknown"))
            color = "green" if status in GREEN else "amber" if status in AMBER else "red" if status in RED else ""
            cells = (
                _relative(item.get("created_at")), item.get("agent_id", "—"), item.get("merchant", "—"),
                f"${float(item.get('amount', 0) or 0):.2f}", status.replace("_", " ").upper(), item.get("reason", "—"),
            )
            body.append("<tr>" + "".join(
                f"<td class='status-{color}'>{html.escape(str(value))}</td>" if index == 4 else
                f"<td>{html.escape(str(value))}</td>" for index, value in enumerate(cells)
            ) + "</tr>")
        st.markdown("<table style='width:100%'><thead><tr>" + "".join(f"<th>{key}</th>" for key in keys) +
                    "</tr></thead><tbody>" + "".join(body) + "</tbody></table>", unsafe_allow_html=True)
    else:
        st.info("No requests in the feed yet.")

    st.subheader("Approval inbox")
    if not pending:
        st.success("Inbox is clear.")
    for item in pending:
        with st.container(border=True):
            st.markdown(f"#### {html.escape(str(item.get('merchant', 'Unknown merchant')))} · <span class='big-amount'>${float(item.get('amount', 0) or 0):.2f}</span>", unsafe_allow_html=True)
            st.write(item.get("reason", "No reason provided"))
            st.info(item.get("explanation") or "Generating explanation...")
            st.caption(f"Expires in {_countdown(item.get('expires_at'))} · Agent {item.get('agent_id', '—')}")
            yes, no = st.columns(2)
            with yes:
                if st.button("Approve", key=f"approve-{item.get('id')}", type="primary", disabled=fixture_mode, use_container_width=True):
                    if _action(st, lambda: sg.approve(item["id"], approver="dashboard")):
                        st.rerun()
            with no:
                if st.button("Deny", key=f"deny-{item.get('id')}", disabled=fixture_mode, use_container_width=True):
                    if _action(st, lambda: sg.reject(item["id"], approver="dashboard")):
                        st.rerun()

    st.subheader("Controls")
    if fixture_mode:
        st.caption("Controls are disabled while viewing fixtures.")
    kill_col, resume_col, reset_col = st.columns(3)
    with kill_col:
        if st.button("🔴 KILL ALL", type="primary", disabled=fixture_mode, use_container_width=True):
            if _action(st, sg.kill):
                st.rerun()
    with resume_col:
        if st.button("Resume", disabled=fixture_mode, use_container_width=True):
            if _action(st, sg.resume):
                st.rerun()
    with reset_col:
        if st.button("Reset demo", disabled=fixture_mode, use_container_width=True):
            if _action(st, sg.reset):
                st.rerun()
    if agents:
        selected = st.selectbox("Agent to stop", options=agents,
                                format_func=lambda agent: agent.get("name", agent.get("id", "Agent")),
                                disabled=fixture_mode)
        if st.button("Kill selected agent", disabled=fixture_mode, key="kill-agent"):
            if _action(st, lambda: sg.kill(selected.get("id"))):
                st.rerun()
        if st.button("Resume selected agent", disabled=fixture_mode, key="resume-agent"):
            if _action(st, lambda: sg.resume(selected.get("id"))):
                st.rerun()


def _render_insights(st, sg, data, fixture_mode):
    usage_tab, trace_tab, team_tab, email_tab = st.tabs(
        ["Model usage", "Workflows", "Team budgets", "Email notifications"])
    with usage_tab:
        totals = data.get("usage_totals", {})
        calls, tokens, cost = st.columns(3)
        calls.metric("Model calls today (UTC)", totals.get("calls", 0))
        tokens.metric("Reported tokens today", totals.get("input_tokens", 0) + totals.get("output_tokens", 0))
        cost.metric("Known cost estimate today", f"${totals.get('estimated_cost', 0):.6f}")
        st.caption("Estimates use application-configured USD rates. Unknown costs are excluded, not assumed free. Recorded after responses; no in-flight model budget guarantee.")
        if totals.get("unpriced_calls", 0):
            st.warning(f"{totals['unpriced_calls']} calls today lack usage data or pricing.")
        st.dataframe(data.get("by_model", []), use_container_width=True)
        with st.expander("Recent model calls (up to 200)"):
            st.dataframe(data.get("usage", []), use_container_width=True)
    with trace_tab:
        traces = data.get("traces", [])
        st.caption("Workflow metadata only; prompts and responses are not recorded here. A completed turn can still have a pending purchase.")
        if traces:
            st.dataframe(traces, use_container_width=True)
            selected_trace = st.selectbox("Workflow", options=[row['id'] for row in traces], key="selected-trace")
            events = [event for event in data.get("events", []) if event['trace_id'] == selected_trace]
            st.dataframe(list(reversed(events)), use_container_width=True)
            st.caption("Shows events from the latest 500 records; request IDs link approvals and execution to their originating workflow.")
        else:
            st.info("No workflow runs recorded yet. Start the updated chatbot and send a message.")
        st.dataframe(data.get("request_context", []), use_container_width=True)
    with team_tab:
        st.caption("Team limits apply atomically across member tool requests. Known model estimates reduce subsequent available funds. Membership is snapshotted per action.")
        st.dataframe(data.get("teams", []), use_container_width=True)
        st.dataframe(data.get("members", []), use_container_width=True)
        if not fixture_mode:
            with st.form("team-settings"):
                team_id = st.text_input("Team ID")
                team_name = st.text_input("Team name (optional)")
                limit = st.number_input("Team daily budget (USD)", min_value=0.0, value=150.0)
                if st.form_submit_button("Save team budget"):
                    if _action(st, lambda: sg.insights.create_team(team_id, limit, team_name or None)):
                        st.rerun()
            agents = sg.status().get("agents", [])
            team_ids = [row['id'] for row in data.get("teams", [])]
            if agents and team_ids:
                with st.form("team-membership"):
                    agent_id = st.selectbox("Assign agent", options=[row['id'] for row in agents])
                    target_team = st.selectbox("To team", options=team_ids)
                    if st.form_submit_button("Assign to team"):
                        if _action(st, lambda: sg.insights.assign_agent(agent_id, target_team)):
                            st.rerun()
    with email_tab:
        st.caption("Request changes and 80% budget warnings enter a durable outbox. Email is sent only when an operator clicks Send / retry. 'sent' means accepted by SMTP, not confirmed inbox delivery.")
        notifications = data.get("notifications", [])
        st.dataframe(notifications, use_container_width=True)
        from spendguard.notifications import EmailSettings, send_pending
        try:
            settings = EmailSettings.from_env()
        except (ValueError, TypeError):
            settings = None
            st.info("Email is not configured. Set SPENDGUARD_SMTP_* values and launch the dashboard with --env-file. Credentials are never shown here.")
        if st.button("Send / retry queued email", disabled=fixture_mode or settings is None):
            try:
                result = send_pending(sg.db_path, settings)
                st.success(f"SMTP accepted {result['sent']} email(s); failed {result['failed']}.")
            except Exception as exc:
                st.error(f"Email batch failed ({type(exc).__name__}).")
        if any(row['status'] == 'sending' for row in notifications):
            st.warning("An interrupted send may have an unknown outcome. Sending rows are not retried automatically; reconcile before resending.")


def main() -> None:
    import streamlit as st

    st.set_page_config(page_title="SpendGuard", page_icon="🛡️", layout="wide")
    if os.getenv("DASHBOARD_FIXTURE") == "1":
        sg = None
    else:
        db_path = os.getenv("SPENDGUARD_DB", "spendguard.db")
        try:
            from spendguard import SpendGuard
            @st.cache_resource
            def get_guard(path: str):
                return SpendGuard(path)
            sg = get_guard(db_path)
        except ImportError as exc:
            st.error(f"SpendGuard core is unavailable: {exc}")
            return

    if hasattr(st, "fragment"):
        @st.fragment(run_every=2)
        def live_view():
            render_dashboard(st, sg)
        live_view()
    else:
        render_dashboard(st, sg)
        time.sleep(2)
        st.rerun()


if __name__ == "__main__":
    main()
