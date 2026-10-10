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
        return {**status, "requests": requests}, pending, False
    except Exception as exc:
        st.error(f"Could not read SpendGuard state: {exc}")
        return {"kill_global": False, "agents": [], "requests": []}, [], False


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
        left = max(0.0, daily - spent - reserved)
        with st.container(border=True):
            st.markdown(f"**{agent.get('name', agent.get('id', 'Agent'))}** · {agent.get('status', 'unknown')}")
            st.progress(min(1.0, (spent + reserved) / daily) if daily else 0.0)
            st.caption(f"Spent ${spent:.2f} · Reserved ${reserved:.2f} · Remaining ${left:.2f} of ${daily:.2f}")

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
