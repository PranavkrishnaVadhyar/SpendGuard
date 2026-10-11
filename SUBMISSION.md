# Project submission

Complete this file during the hackathon and use it to prepare your submission through the method announced by the organizers. Do not submit your project to the template repository.

## Project

- **Project name:** SpendGuard
- **Short description:** Local spending controls for AI agents, with individual/shared budgets, human approvals, LangChain tools, model usage estimates, workflow traces, and an email outbox. Developers and operators can inspect and govern declared agent spending through a dashboard.
- **Code repository URL:** TODO
- **Final submitted implementation commit SHA:** TODO
- **Working demo URL or local demo steps:** Local offline walkthrough in [dashboard guide](docs/dashboard.md); browser walkthrough pending human verification.
- **Demo access requirements:** Python environment with LangChain and Streamlit; offline demo needs no credentials. Live chatbot requires OpenAI configuration; email requires operator-supplied SMTP settings. No hosted demo has been published.

## Participants

Participate solo or in a team of up to 4. Remove unused rows.

| Participant name | GitHub handle | Contribution |
| --- | --- | --- |
| TODO | TODO | TODO |

## Run and demonstrate

- **Prerequisites and versions:** Python 3.10+; local validation used Python 3.14.3, LangChain 1.4.4, and Streamlit 1.65.0.
- **Install command:** `python -m pip install -e ".[dev]"`; live chatbot additionally uses `python -m pip install -r sample_app/requirements-chatbot.txt`.
- **Required environment variable names:** None for the offline demo. Live setup uses the blank [sample environment template](sample_app/.env.example); keep the real `.env` ignored.
- **Start command:** `python sample_app/dashboard_demo.py --reset`, then `python -m spendguard.cli --db sample_app/dashboard_demo.db dashboard`.
- **Demo walkthrough:** Open localhost:8501; inspect individual/team budgets, known synthetic model estimates, workflow/request links, one pending approval and a shared-budget denial, and the queued notification outbox. Reject a pending request to release its reservation. The offline demo never sends email.
- **Checks performed and results:** 142 tests passed in 22.67s, including concurrent team reservations, workflow linkage, model tracking, mocked email retries, and Streamlit rendering/rejection. Standalone wheel built/inspected with 22 runtime files and optional-only dependencies. Core imports without optional site-packages. No live provider calls or emails used.
- **Known limitations or incomplete features:** Simulated payment tools; after-response model estimates without pre-call cost reservations or invoice reconciliation; unknown costs may overstate remaining funds; local trusted interfaces lack authentication. SMTP acceptance is not confirmed delivery. Interrupted execution/email outcomes require reconciliation. Live browser/model/email demo remains unverified; participant/repository/final-submission details still need human completion.
- **Libraries, APIs, and public datasets used:** [Core dependencies](docs/core.md), [LangChain integration](docs/langchain.md), and [insights sources](docs/insights.md); no public dataset or external project implementation imported.
- **AI usage record:** [AI_USAGE.md](AI_USAGE.md)
- **Development change log:** [CHANGELOG.md](CHANGELOG.md)

## Submission checklist

- [ ] The project implementation started from scratch at the event.
- [ ] I participated solo or with no more than 4 team members in total.
- [ ] Codex was used during development and its usage is documented.
- [ ] The code repository URL, short description, and working demo are provided.
- [ ] README setup and demo instructions match the submitted code.
- [ ] Actual checks and known limitations are documented.
- [ ] Meaningful changes are documented and committed throughout development.
- [ ] The final implementation is committed and pushed, and its SHA is recorded above.
- [ ] No credentials or private data are included in the repository or demo instructions.
- [ ] The organizers' announced submission method and timing have been followed.

Event reference: [DevDay Exchange Community: Kochi on Luma](https://luma.com/z10nz8gp). The event wraps up by **10:00 AM IST on 11 October 2026**.
