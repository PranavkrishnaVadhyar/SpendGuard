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

SpendGuard's Python library core has been migrated from the earlier backend. It has not been executed or tested, at the user's request. The documentation and commit cadence are repository workflow guidance; the event participation rules are in [RULES.md](RULES.md).

## Project overview — complete during the event

- **Project name:** SpendGuard
- **Short description:** A Python library for agent spend controls with deterministic budgets, human approvals, and kill switches. Payments are mocked by default.
- **Team:** TODO — participant names and GitHub handles; maximum 4 members.
- **Working demo:** Not yet verified; see [library setup](docs/core.md).
- **Technology stack:** Python 3.10+ standard library and SQLite; setuptools packaging.

### Run the project

Local setup is installed in `.venv` using Python 3.14.3 and
`pip install -e ".[dev]"`. `pip check` reported no broken requirements on
11 October 2026. The full test suite passed: 79 tests in 10.14 seconds on
11 October 2026. An interactive demo has not been verified.
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

### Current status

- Implemented features: dataclass models, policy evaluation, atomic reservations, agent/policy management, request feed, approvals, expiry, polling, kill/resume, reset, background hooks, adapters, CLI, and dashboard. All 79 current tests pass, including thread/process budget checks; interactive dashboard behavior remains unverified.
- Known limitations: default execution is a mock; automated tool wrappers are still absent. A consumer sample is provided in `sample_app/` but its execution and interactive approval remain unverified. Interrupted execution recovery is not implemented. Source review identified unresolved executor configuration, adapter success validation, dashboard read-error display, and CLI error-handling issues that the passing tests do not cover.
- Libraries and sources: listed in [core documentation](docs/core.md); no public dataset used.

See [AI_USAGE.md](AI_USAGE.md) for AI assistance and [CHANGELOG.md](CHANGELOG.md) for the development record.
