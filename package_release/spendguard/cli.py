"""Command line interface for inspecting and managing a SpendGuard database."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="spendguard")
    parser.add_argument("--db", default=os.getenv("SPENDGUARD_DB", "spendguard.db"), help="SQLite database path")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="Show kill state and agent budgets")
    feed = commands.add_parser("feed", help="Show recent requests")
    feed.add_argument("--limit", type=int, default=50)
    commands.add_parser("pending", help="Show pending approvals")
    for name in ("approve", "reject"):
        command = commands.add_parser(name)
        command.add_argument("id")
        command.add_argument("--approver", default="admin")
    kill = commands.add_parser("kill")
    kill.add_argument("--agent", help="Agent id; omit to stop all agents")
    resume = commands.add_parser("resume")
    resume.add_argument("--agent", help="Agent id; omit to resume all agents")
    dashboard = commands.add_parser("dashboard", help="Start the Streamlit dashboard")
    dashboard.add_argument("--db", dest="dashboard_db")
    dashboard.add_argument("--port", type=int, default=8501)
    return parser


def _record_dict(record) -> dict:
    return record.to_dict() if hasattr(record, "to_dict") else dict(record)


def _print_requests(records: list, *, include_explanation: bool = False) -> None:
    if not records:
        print("No requests.")
        return
    for record in records:
        item = _record_dict(record)
        print(f"{item.get('id')}  {item.get('agent_id')}  {item.get('merchant')}  "
              f"${float(item.get('amount', 0)):.2f}  {item.get('status')}  {item.get('reason', '')}")
        if include_explanation:
            print(f"  Explanation: {item.get('explanation') or '—'}")
            print(f"  Expires: {item.get('expires_at') or '—'}")


def _run_dashboard(db_path: str, port: int) -> int:
    try:
        import streamlit  # noqa: F401 - optional dependency check
    except ImportError:
        print('Dashboard requires Streamlit. Install it with: pip install "spendguard[dashboard]"', file=sys.stderr)
        return 1
    app = Path(__file__).parent / "dashboard" / "app.py"
    env = os.environ.copy()
    env["SPENDGUARD_DB"] = db_path
    try:
        return subprocess.call([
            sys.executable, "-m", "streamlit", "run", str(app), "--server.port", str(port)
        ], env=env)
    except OSError as exc:
        print(f"Could not start dashboard: {exc}", file=sys.stderr)
        return 1


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    db_path = getattr(args, "dashboard_db", None) or args.db
    if args.command == "dashboard":
        return _run_dashboard(db_path, args.port)
    try:
        from spendguard import InvalidState, NotFound, SpendGuard
        guard = SpendGuard(db_path)
        if args.command == "status":
            status = guard.status()
            print(f"Global kill: {'KILLED' if status.get('kill_global') else 'OK'}")
            for agent in status.get("agents", []):
                spent = float(agent.get("spent", 0) or 0)
                reserved = float(agent.get("reserved", 0) or 0)
                budget = float(agent.get("daily_budget", 0) or 0)
                print(f"{agent.get('id')}  {agent.get('name', '')}  {agent.get('status', '')}  "
                      f"spent ${spent:.2f}  reserved ${reserved:.2f}  remaining ${max(0, budget-spent-reserved):.2f}")
        elif args.command == "feed":
            _print_requests(guard.feed(args.limit))
        elif args.command == "pending":
            _print_requests(guard.pending(), include_explanation=True)
        elif args.command in {"approve", "reject"}:
            method = guard.approve if args.command == "approve" else guard.reject
            result = method(args.id, approver=args.approver)
            record = _record_dict(result)
            print(f"{args.command.title()} request {args.id}: {record.get('status')}")
        elif args.command == "kill":
            guard.kill(args.agent)
            print(f"Kill set for {args.agent or 'all agents'}.")
        elif args.command == "resume":
            guard.resume(args.agent)
            print(f"Resumed {args.agent or 'all agents'}.")
        return 0
    except ImportError as exc:
        print(f"SpendGuard core is unavailable: {exc}", file=sys.stderr)
        return 1
    except (NotFound, InvalidState) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
