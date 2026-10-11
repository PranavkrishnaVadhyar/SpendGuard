"""Seed an isolated dashboard demo with explicitly synthetic model usage; no network."""

import argparse
from pathlib import Path
from uuid import uuid4

from langchain_core.tools import tool

from spendguard import Policy, SpendGuard
from spendguard.integrations.langchain import wrap_tool


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, default=Path(__file__).with_name('dashboard_demo.db'))
    parser.add_argument('--reset', action='store_true', help='Clear only the selected demo database')
    args = parser.parse_args(argv)
    guard = SpendGuard(args.db, explainer=lambda *args: 'Offline demo: review the declared purchase cost.')
    if args.reset:
        guard.reset()
    guard.insights.create_team('demo-team', 50, 'Offline demo team')
    for agent in ('demo-research', 'demo-analysis'):
        guard.create_agent(agent, Policy(100, 100, 25, ['credits.example']))
        guard.insights.assign_agent(agent, 'demo-team')

    @tool
    def buy_demo(quantity: int) -> dict:
        """Simulate a credit purchase without contacting any provider."""
        return {'credits': quantity, 'simulated': True}

    session = str(uuid4())
    for agent, quantity in [('demo-research', 1), ('demo-analysis', 3), ('demo-research', 2)]:
        trace = guard.insights.start_trace(agent, 'OFFLINE DEMO: synthetic usage', session)
        guard.insights.record_model_usage(agent, str(uuid4()), 'synthetic-demo-model', 100, 50,
                                         trace_id=trace, input_rate=1, output_rate=2)
        guard.insights.event(trace, 'model', 'synthetic-demo-model', 'simulated')
        wrapped = wrap_tool(buy_demo, guard, agent_id=agent, merchant='credits.example',
                            amount=quantity * 10, wait_timeout=0)
        result = wrapped.invoke({'quantity': quantity}, config={'metadata': {'spendguard_trace_id': trace}})
        guard.insights.finish_trace(trace)
        print(agent, result['status'], 'request', result['request_id'])
    guard.insights.snapshot()  # Materialize the shared-budget warning.
    print('Offline demo only: synthetic model usage and simulated purchases. No email sent.')
    print('Database:', guard.db_path)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
