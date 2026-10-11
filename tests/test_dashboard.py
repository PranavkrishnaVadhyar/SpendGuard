from pathlib import Path

import pytest

pytest.importorskip('streamlit')
from streamlit.testing.v1 import AppTest
from spendguard import Policy, SpendGuard


def test_dashboard_insight_tabs_and_approval(tmp_path, monkeypatch):
    database = tmp_path / 'dashboard.db'
    guard = SpendGuard(database, explainer=lambda *args: None)
    guard.create_agent('agent', Policy(100, 100, 25, ['credits.example']))
    guard.insights.create_team('team', 150)
    guard.insights.assign_agent('agent', 'team')
    trace = guard.insights.start_trace('agent')
    guard.insights.record_model_usage('agent', 'model-call', 'local-test', 100, 50,
                                     trace_id=trace, input_rate=1, output_rate=2)
    guard.insights.finish_trace(trace)
    held = guard.request('agent', 'credits.example', 30)
    monkeypatch.setenv('SPENDGUARD_DB', str(database))
    monkeypatch.delenv('DASHBOARD_FIXTURE', raising=False)
    monkeypatch.delenv('SPENDGUARD_SMTP_HOST', raising=False)
    app_path = Path(__file__).parents[1] / 'spendguard/dashboard/app.py'
    app = AppTest.from_file(str(app_path), default_timeout=15).run()
    assert not app.exception
    assert [tab.label for tab in app.tabs] == ['Model usage', 'Workflows', 'Team budgets', 'Email notifications']
    assert next(button for button in app.button if button.label == 'Send / retry queued email').disabled
    next(button for button in app.button if button.label == 'Deny').click().run()
    assert not app.exception
    assert guard.get(held.request_id).status == 'rejected'


def test_dashboard_read_failure_never_reports_healthy_state():
    from spendguard.dashboard.app import render_dashboard

    class FakeUI:
        errors = []

        def markdown(self, *args, **kwargs):
            pass

        def error(self, message):
            self.errors.append(message)

    class BrokenGuard:
        def status(self):
            raise RuntimeError('private-details')

    ui = FakeUI()
    render_dashboard(ui, BrokenGuard())
    assert ui.errors and 'private-details' not in ui.errors[0]
