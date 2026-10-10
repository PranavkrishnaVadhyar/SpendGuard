# DevDay Exchange Community Hackathon: Kochi

A repository template for participants at the 10–11 October 2026 hackathon. It contains event rules and documentation scaffolding; build your project from scratch at the event.

**[Event and registration on Luma](https://luma.com/z10nz8gp)** · **[Event rules](RULES.md)** · **[Agent instructions](AGENTS.md)**

## Event details

| Detail | Information |
| --- | --- |
| Venue | JAIN University, Kochi |
| Location | [Open the venue map](https://maps.app.goo.gl/Eme7gR7NDXSNRANu5) |
| Rooms | 2008 and 2009 |
| Check-in | 10 October 2026, 6:00 PM IST |
| Kick-off | 10 October 2026, 6:30 PM IST |
| Wrap-up | 11 October 2026, by 10:00 AM IST |
| Participation | Solo or a team of up to 4 participants |
| Theme | Open — build anything you like |

Keep your approved Luma QR code ready for entry, and bring your laptop and charger. Eligible checked-in participants will receive Codex credits and OpenAI API credits.

## Use this template

1. Select **Use this template → Create a new repository** on GitHub. Create your own project repository and clone it.
2. Read [RULES.md](RULES.md) and [AGENTS.md](AGENTS.md) before building. Begin project implementation at the event.
3. Fill in the project overview below as you build. Use any suitable language or framework, keeping the implementation simple.
4. Record meaningful changes in [CHANGELOG.md](CHANGELOG.md) and your Codex usage in [AI_USAGE.md](AI_USAGE.md). Commit after completed milestones; aim for a meaningful checkpoint about every 30 minutes.
5. Complete [SUBMISSION.md](SUBMISSION.md) with your code repository, short project description, and working demo. Follow submission instructions announced by the organizers.

SpendGuard's Python library core has been migrated from the earlier backend and tested. The documentation and commit cadence are repository workflow guidance; the event participation rules are in [RULES.md](RULES.md).

## Project overview — complete during the event

- **Project name:** SpendGuard
- **Short description:** A Python library for agent spend controls with deterministic budgets, human approvals, and kill switches. Payments are mocked by default.
- **Team:** TODO — participant names and GitHub handles; maximum 4 members.
- **Working demo:** Not yet verified; see [library setup](docs/core.md).
- **Technology stack:** Python 3.10+ standard library and SQLite; setuptools packaging.

### Run the project

Local setup is installed in `.venv` using Python 3.14.3 and
editable SpendGuard. LangChain 1.4.4 is installed for the optional integration.
All 113 tests passed in 13.75 seconds, and the offline LangChain example ran
successfully. See the changelog for validation details. An interactive dashboard demo has not
been verified. Refreshing the editable installation currently encounters a
Windows lock on `.venv/Scripts/spendguard.exe`; close processes using that
executable before reinstalling. Module commands remain available through
`python -m spendguard.cli`.
To reproduce the setup:

1. Install Python 3.10+ and create a virtual environment: `python -m venv .venv`.
2. Install the core: `.\.venv\Scripts\python -m pip install -e .`.
3. For tests, install pytest: `.\.venv\Scripts\python -m pip install pytest`. Optional full extras: `.\.venv\Scripts\python -m pip install -e ".[dev]"`.
4. Use `from spendguard import SpendGuard, Policy`, construct a guard with a database path, then call `create_agent` and `request`; see the complete [example](docs/core.md).
5. Run tests when authorized: `.\.venv\Scripts\python -m pytest -q`.

Construction creates tables without demo agents or wiping data. The core does
not load `.env`; pass configuration directly. The trimmed `.env.example` is for
optional integrations. See [docs/core.md](docs/core.md) for the API, dependency
sources, and limitations. Use a new database path if an old schema exists.

A complete consumer example is in [sample_app](sample_app/README.md). Run
`.\.venv\Scripts\python.exe sample_app\main.py --reset` from this folder for
allow/hold/deny examples, or add `--wait` to wait for a dashboard decision.
Its database is separate at `sample_app/sample.db`.
To use it as another developer's standalone project, follow the sample README
from inside `sample_app/`: create its own environment and install SpendGuard as
a dependency from the parent checkout or a separately supplied source path.

[package_release](package_release/README.md) is a standalone package snapshot
containing only the distributable library, package metadata, and package README.
Copy that directory to build or install independently. Future source changes in
`spendguard/` must be copied into that snapshot before a new release is built.

LangChain agents can use [guarded tools](docs/langchain.md). Install
`python -m pip install -e ".[langchain]"`, import
`wrap_tool` from `spendguard.integrations.langchain`, and pass wrapped tools to
`create_agent`. The offline example is `python sample_app/langchain_agent.py`.
Allowed calls execute the real wrapped function; held calls require approval
and execution by the waiting or resumed wrapper. The core dependency set is
unchanged.

An interactive [sample chatbot](sample_app/CHATBOT.md) now uses a configured
OpenAI model through LangChain, keeps in-session chat history, and wraps demo
credit purchases with SpendGuard. Operator commands approve/reject, inspect
balances, and stop spending. Install its separate `requirements-chatbot.txt`
and set `OPENAI_API_KEY`/`OPENAI_MODEL`; purchases are simulated and model API
costs are outside SpendGuard's budget. Live model calls have not been verified.

### Current status

- Implemented features: dataclass models, policy evaluation, atomic reservations, agent/policy management, request feed, approvals, expiry, polling, kill/resume, reset, background hooks, adapters, CLI, dashboard, and optional LangChain tool wrapping. Tests include thread/process budget checks and LangChain agent execution; interactive dashboard behavior remains unverified.
- Known limitations: default payment adapters are mocks; LangChain wrappers execute the supplied tool implementation. Only synchronous StructuredTool tools with Pydantic schemas are supported, with `ainvoke` through worker threads. Model inference costs and unwrapped actions are not tracked. Interrupted execution recovery is not implemented. Source-review findings about ordinary custom-executor configuration, adapter success validation, dashboard read-error display, and CLI error handling remain unresolved; wrapped tool approvals are deferred safely to their wrapper.
- Libraries and sources: listed in [core documentation](docs/core.md); no public dataset used.

See [AI_USAGE.md](AI_USAGE.md) for AI assistance and [CHANGELOG.md](CHANGELOG.md) for the development record.
