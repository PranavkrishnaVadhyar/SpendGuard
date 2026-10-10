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

SpendGuard's FastAPI backend has now been authored. It has not been executed or tested yet, at the user's request. The documentation and commit cadence are repository workflow guidance; the event participation rules are in [RULES.md](RULES.md).

## Project overview — complete during the event

- **Project name:** SpendGuard
- **Short description:** A spend-control gateway for AI agents with deterministic budgets, human approvals, and kill switches. Payments are mocked.
- **Team:** TODO — participant names and GitHub handles; maximum 4 members.
- **Working demo:** Not yet verified; see [backend setup](docs/backend.md).
- **Technology stack:** Python 3.11+, FastAPI, Pydantic v2, SQLite, Uvicorn.

### Run the project

Commands below are provided for later use and have not been run:

1. Install Python 3.11+ and create a virtual environment: `python -m venv .venv`.
2. Install dependencies: `.\.venv\Scripts\python -m pip install -r requirements.txt`.
3. Copy `.env.example` to `.env` if absent; configure `ADMIN_KEY`, `DB_PATH`, and `APPROVAL_TTL_SECONDS`.
4. Start: `.\.venv\Scripts\python -m uvicorn gateway.main:app --reload --port 8000`.
5. Tests: `.\.venv\Scripts\python -m pytest -q`.

Startup generates the ignored `.demo_token` for agent authentication. See
[docs/backend.md](docs/backend.md) for the HTTP contract, integration details,
dependency sources, and limitations.

### Current status

- Authored features (unverified): policy evaluation, atomic reservations, agent/admin authentication, request feed, approvals, expiry, kill/resume, reset, and backend tests.
- Known limitations: no runtime checks performed; payment and explanation fallbacks are local mocks; dashboard, SDK, and demo agent remain separate teammates' work. In-flight execution recovery is not implemented.
- Libraries and sources: listed in [backend documentation](docs/backend.md); no public dataset used.

See [AI_USAGE.md](AI_USAGE.md) for AI assistance and [CHANGELOG.md](CHANGELOG.md) for the development record.
