from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from spendguard import SpendGuard, Policy, InvalidState, db
from spendguard.notifications import EmailSettings, send_pending


@pytest.fixture
def guard(tmp_path):
    sg = SpendGuard(tmp_path / 'insights.db', executor=lambda req: {'ok': True}, explainer=lambda *args: None)
    for agent in ('a', 'b'):
        sg.create_agent(agent, Policy(100, 100, 25, ['credits.example']))
    sg.insights.create_team('team', 50)
    for agent in ('a', 'b'):
        sg.insights.assign_agent(agent, 'team')
    return sg


def test_shared_budget_is_atomic_across_agents(guard):
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda i: guard.request('a' if i % 2 else 'b', 'credits.example', 10), range(12)))
    assert sum(r.status == 'settled' for r in results) == 5
    assert any(r.reason == 'team budget exceeded' for r in results)
    team = guard.insights.snapshot()['teams'][0]
    assert team['spent'] == 50 and team['available'] == 0


def test_team_reservations_and_membership_snapshot(guard):
    held = guard.request('a', 'credits.example', 30)
    assert held.status == 'pending_approval'
    assert guard.request('b', 'credits.example', 30).reason == 'team budget exceeded'
    guard.insights.create_team('other', 100)
    guard.insights.assign_agent('a', 'other')
    teams = {row['id']: row for row in guard.insights.snapshot()['teams']}
    assert teams['team']['reserved'] == 30 and teams['other']['reserved'] == 0
    guard.reject(held.request_id)
    assert guard.insights.snapshot()['teams'][1]['reserved'] == 0


def test_usage_cost_unknowns_dedup_and_budget(guard):
    trace = guard.insights.start_trace('a')
    guard.insights.record_model_usage('a', 'call-1', 'model', 1_000_000, 0,
                                     trace_id=trace, input_rate=40, output_rate=10)
    guard.insights.record_model_usage('a', 'call-1', 'model', 1_000_000, 0,
                                     trace_id=trace, input_rate=40, output_rate=10)
    guard.insights.record_model_usage('a', 'unknown', 'model', usage_known=False)
    assert guard.status()['agents'][0]['available'] == 60
    snapshot = guard.insights.snapshot()
    assert snapshot['usage_totals']['calls'] == 2
    assert snapshot['usage_totals']['estimated_cost'] == 40
    assert snapshot['usage_totals']['unpriced_calls'] == 1
    assert snapshot['teams'][0]['available'] == 10
    assert guard.request('b', 'credits.example', 20).reason == 'team budget exceeded'
    with pytest.raises(ValueError, match='different model call'):
        guard.insights.record_model_usage('b', 'call-1', 'model')


@pytest.mark.parametrize('kwargs', [dict(input_tokens=-1), dict(input_tokens=True), dict(input_rate=float('nan')),
                                    dict(output_rate=-1), dict(usage_known='yes')])
def test_invalid_usage_rejected(guard, kwargs):
    with pytest.raises(ValueError):
        guard.insights.record_model_usage('a', 'bad', 'model', **kwargs)


def test_daily_totals_ignore_old_records(guard):
    guard.insights.record_model_usage('a', 'old', 'model', 100, 20, input_rate=10, output_rate=20)
    with db.transaction(guard.db_path) as conn:
        conn.execute("UPDATE model_usage SET created_at='2000-01-01T00:00:00Z'")
    assert guard.insights.snapshot()['usage_totals']['calls'] == 0
    assert guard.status()['agents'][0]['model_estimated_cost'] == 0


def test_trace_links_follow_approval_and_execution(guard):
    pytest.importorskip('langchain')
    from langchain_core.tools import tool
    from spendguard.integrations.langchain import wrap_tool

    @tool
    def purchase(quantity: int) -> str:
        """Local purchase."""
        return 'done'

    trace = guard.insights.start_trace('a')
    wrapped = wrap_tool(purchase, guard, agent_id='a', merchant='credits.example', amount=30, wait_timeout=0)
    config = {'metadata': {'spendguard_trace_id': trace, 'spendguard_idempotency_key': 'order'}}
    held = wrapped.invoke({'quantity': 3}, config=config)
    guard.insights.finish_trace(trace)
    SpendGuard(guard.db_path).approve(held['request_id'])
    assert wrapped.invoke({'quantity': 3}, config=config)['status'] == 'settled'
    events = guard.insights.snapshot()['events']
    assert {e['status'] for e in events} >= {'pending_approval', 'approved', 'executing', 'settled'}
    assert all(e['trace_id'] == trace for e in events)


def test_wrong_agent_trace_denies_and_rolls_back(guard):
    trace = guard.insights.start_trace('b')
    result = guard._request('a', 'credits.example', 10, tool_call={'name': 'tool', 'arguments': '{}', 'trace_id': trace})
    assert result.status == 'denied' and result.request_id is None
    assert guard.feed() == []


def test_budget_alerts_deduplicate_and_reset_retains_teams(guard):
    for _ in range(4):
        guard.request('a', 'credits.example', 10)
    first = guard.insights.snapshot()['notifications']
    second = guard.insights.snapshot()['notifications']
    assert len(first) == len(second)
    assert sum(row['event_key'].startswith('budget:team:') for row in first) == 1
    trace = guard.insights.start_trace('a')
    with pytest.raises(InvalidState, match='agent run'):
        guard.reset()
    guard.insights.finish_trace(trace, 'failed')
    guard.reset()
    snapshot = guard.insights.snapshot()
    assert snapshot['teams'] and snapshot['members']
    assert not snapshot['notifications'] and not snapshot['usage'] and not snapshot['traces']


class FakeSMTP:
    messages = []
    fail = False

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def starttls(self, **kwargs):
        pass

    def login(self, *args):
        pass

    def send_message(self, message):
        if self.fail:
            raise RuntimeError('secret-provider-detail')
        self.messages.append(message)
        return {}


def test_email_outbox_failure_retry_and_no_duplicate(guard, monkeypatch):
    import spendguard.notifications as notification_module
    monkeypatch.setattr(notification_module.smtplib, 'SMTP', FakeSMTP)
    monkeypatch.setattr(FakeSMTP, 'messages', [])
    monkeypatch.setattr(FakeSMTP, 'fail', True)
    held = guard.request('a', 'credits.example', 30)
    settings = EmailSettings('smtp.example', 587, 'sender@example.test', 'reviewer@example.test')
    assert send_pending(guard.db_path, settings) == {'sent': 0, 'failed': 1}
    row = guard.insights.snapshot()['notifications'][0]
    assert row['error_type'] == 'RuntimeError' and 'secret' not in str(row)
    monkeypatch.setattr(FakeSMTP, 'fail', False)
    assert send_pending(guard.db_path, settings) == {'sent': 1, 'failed': 0}
    assert send_pending(guard.db_path, settings) == {'sent': 0, 'failed': 0}
    assert len(FakeSMTP.messages) == 1
    assert str(held.request_id) in FakeSMTP.messages[0].get_content()


def test_interrupted_email_is_not_blindly_retried(guard):
    guard.request('a', 'credits.example', 30)
    with db.transaction(guard.db_path) as conn:
        conn.execute("UPDATE notifications SET status='sending'")
    result = send_pending(guard.db_path, EmailSettings('smtp.example', 587, 'a@b.test', 'c@d.test'))
    assert result == {'sent': 0, 'failed': 0}
    with pytest.raises(InvalidState, match='email send'):
        guard.reset()


def test_langchain_usage_callback_records_tokens(guard):
    pytest.importorskip('langchain')
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import LLMResult, ChatGeneration
    from spendguard.integrations.usage import UsageTracker
    trace = guard.insights.start_trace('a')
    tracker = UsageTracker(guard.insights, 'a', trace, 'test-model', 1, 2)
    message = AIMessage(content='Not stored', usage_metadata={'input_tokens': 100, 'output_tokens': 50, 'total_tokens': 150})
    tracker.on_llm_end(LLMResult(generations=[[ChatGeneration(message=message)]]), run_id=uuid4())
    snapshot = guard.insights.snapshot()
    assert snapshot['usage_totals']['estimated_cost'] == pytest.approx(0.0002)
    assert snapshot['usage_totals']['input_tokens'] == 100
    assert 'Not stored' not in str(snapshot)


def test_email_headers_and_security_validate():
    with pytest.raises(ValueError):
        EmailSettings('smtp.example', 587, 'a\nBcc:c', 'b@example.test')
    with pytest.raises(ValueError):
        EmailSettings('smtp.example', 587, 'a@example.test', 'b@example.test', security='plain')


def test_synthetic_dashboard_demo_has_shared_budget_denial(tmp_path):
    pytest.importorskip('langchain')
    from sample_app.dashboard_demo import main
    database = tmp_path / 'demo.db'
    assert main(['--db', str(database), '--reset']) == 0
    guard = SpendGuard(database)
    assert {row.status for row in guard.feed()} == {'settled', 'pending_approval', 'denied'}
    snapshot = guard.insights.snapshot()
    assert snapshot['usage_totals']['calls'] == 3
    assert len(snapshot['traces']) == 3
    assert snapshot['teams'][0]['reserved'] == 30


def test_password_does_not_appear_in_settings_repr():
    settings = EmailSettings('smtp.example', 587, 'a@b.test', 'c@d.test', 'user', 'private-password')
    assert 'private-password' not in repr(settings)


def test_failed_model_call_stays_unknown_without_error_content(guard):
    pytest.importorskip('langchain')
    from spendguard.integrations.usage import UsageTracker
    trace = guard.insights.start_trace('a')
    tracker = UsageTracker(guard.insights, 'a', trace, 'model', 1, 2)
    tracker.on_llm_error(RuntimeError('private-provider-detail'), run_id=uuid4())
    snapshot = guard.insights.snapshot()
    assert snapshot['usage_totals']['unpriced_calls'] == 1
    assert snapshot['usage'][0]['estimated_cost'] is None
    assert 'private-provider-detail' not in str(snapshot)
