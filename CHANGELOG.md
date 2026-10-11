# Change log

Record each meaningful project change during the event, newest first. Update this file in the same commit as the change. Use a real timestamp with timezone, for example `YYYY-MM-DDTHH:MM:SS+05:30`.

## Event build log

## 2026-10-11T06:54:50+05:30 — Generate chatbot order UUIDs automatically

- Changed: Made the model-facing purchase tool's order ID optional and generate a UUID in application code before submitting a new purchase. Included the ID in all purchase results and preserved it through operator approval/resume and explicit retries. Updated system/tool instructions, prompt examples, root README, and chatbot guide; existing explicit IDs still work.
- Why: Users can request a purchase without inventing an identifier while retaining idempotency for a known order.
- Validation: All 24 chatbot tests passed in 5.55s with scripted LangChain models and temporary databases, including omitted IDs for settle/hold/deny, distinct UUIDs for separate purchases, retry deduplication, and approval preserving the generated ID. Diff whitespace reviewed. No live API calls or payments; no core/package runtime changes or release archive rebuild needed.
- Limitations: Omitting an ID always creates a new order; conversational retries rely on the model reusing the returned ID. Ambiguous retry intent must be clarified. Conversation/session mapping remains in memory; restart recovery uses the saved order ID/quantity as documented. Human review pending.

## 2026-10-11T06:32:00+05:30 — Prepare spnd-guard for PyPI

- Changed: Renamed the distribution in root and standalone metadata to `spnd-guard` version 0.1.0, preserving Python imports, CLI, configuration, and database compatibility. Added README metadata at the root, alpha/OS/Python classifiers, keywords, verified repository URLs, consumer install examples, and `docs/publishing.md` with secure PyPI/TestPyPI upload and verification steps.
- Why: Publish under the user's requested install name while preserving existing integrations.
- Validation: Installed build 1.6.1 and Twine 7.0.0. Isolated build produced `package_release/dist/spnd_guard-0.1.0-py3-none-any.whl` and `spnd_guard-0.1.0.tar.gz`; both passed `twine check --strict`. Verified distribution metadata, optional-only dependencies, CLI entry point, archive exclusions, and all 22 runtime files against source/snapshot/wheel/sdist. Installed the wheel with no dependencies in a fresh virtual environment, then verified version, imports, local mock settlement/denial, and CLI help with isolated Python outside the source import path. PyPI JSON lookup returned HTTP 404 for the requested name; this does not guarantee name availability. Diff whitespace checked. Runtime code unchanged; full 142-test suite from the prior milestone not repeated.
- Limitations: No upload or index installation performed; authentication is not configured in the usual local environment/config file. No license/author identity invented. Declared Python 3.10+ support was only exercised on local Python 3.14. Existing development environment retains its previous distribution to avoid CLI file-lock/shared-import conflicts; wheel was checked in a fresh environment. Credentials, release artifacts, temporary validation environment, and user `test.py` are excluded from the commit. Human review pending; no push.

## 2026-10-11T04:59:36+05:30 — Expand dashboard with usage, workflows, teams, and email

- Changed: Added durable model-usage estimates, workflow/session/tool events and request transitions, atomic shared team budgets with membership snapshots, and an SMTP notification outbox with explicit send/retry and sanitized failures. Expanded Streamlit tabs/forms and CLI insights/env-file support; integrated tracking into the chatbot and preserved dashboard team edits across restarts. Added a separate offline dashboard demo, blank pricing/SMTP settings, 25 new tests, and updated root/core/dashboard/LangChain/sample/release/submission documentation. Synchronized 22 runtime files into `package_release/` while keeping the core standard-library-only.
- Why: Make agent spending inspectable across model and tool activity, enforce shared limits, connect purchases to workflows, and notify reviewers by email (per the user's correction), without automatic external messages or invented usage/prices.
- Validation: Final full suite passed: 142 tests in 22.67s. Coverage includes concurrent shared reservations, membership snapshots, known/unknown/deduplicated model usage, workflow/approval/execution linkage, mocked SMTP failure/retry/ambiguous sending, CLI env loading/errors, chatbot restart/context, explicit synthetic offline demo, and Streamlit tab rendering/rejection. Built/inspected a standalone wheel with optional-only dependencies and 22 runtime files; core imported without site-packages. Source/snapshot bytes, local doc links, ignored secret files, dependency consistency, and diff whitespace checked. `pip check` found no broken requirements, with the existing invalid-distribution warning from the earlier interrupted reinstall. No real model call, email, payment, deployment, or push occurred.
- Cleanup: Removed 12 generated cache/build artifacts or directories, including bytecode, stale validation wheel/scripts, and build metadata. Verified all four inventoried README files survived cleanup unchanged; README content was updated separately for the new features. Retained useful examples, fixtures, tests, event records, and the user's untracked `test.py`. Removed an unused optional import for a nonexistent tools module. Also fixed malformed truthy adapter success, dashboard false-healthy reads, and expected CLI error handling identified in the earlier review.
- Limitations: Model estimates are after-response accounting using configured USD rates, without pre-call reservation, cached-rate handling, invoice reconciliation, or guaranteed model-spend caps. Unknown/uninstrumented calls can overstate remaining funds. Membership applies to newly created records; old unassigned actions are not retroactively charged to teams. Budget warnings queue on report refresh; emails send only on explicit operator action and SMTP acceptance is not inbox delivery. Interrupted execution/traces/email sends require manual reconciliation. Live browser/provider/email paths remain unverified, and local interfaces have no authentication. SMTP settings remain blank until supplied by the user. Human review and participant/repository/final-submission details remain pending.

## 2026-10-11T04:29:35+05:30 — Load chatbot configuration from an environment file

- Changed: Added python-dotenv to chatbot-only requirements and automatic loading of `sample_app/.env`, with an optional `--env-file` path. Terminal variables override file values; `--model` overrides both. Added a blank `sample_app/.env.example`, four loading/precedence cases, test isolation from real credentials, and updated setup documentation. Created/populated the ignored chatbot `.env` from existing local configuration without displaying credential values; preserved existing nonempty chatbot settings.
- Why: Let the chatbot start using a local configuration file instead of requiring API settings to be entered in each terminal session.
- Validation: Installed python-dotenv 1.2.4; chatbot tests passed (21 in 3.35s); full suite passed (117 in 13.16s). Verified CLI help, Git ignores for the real `.env`, blank example, documentation links, and diff whitespace. `pip check` found no broken requirements, with the existing invalid-distribution warning from an earlier interrupted install. No live model calls or payments were made.
- Limitations: Keys/models were copied locally but not verified with the provider. Existing environment variables (including empty ones) take priority over file values. Configuration loading is limited to the chatbot sample; core library and other examples retain their behavior. Human review pending; real `.env` excluded from Git; user `test.py` preserved.

## 2026-10-11T03:46:08+05:30 — Add interactive guarded chatbot sample

- Changed: Added `sample_app/chatbot.py`, chatbot-only requirements and setup guide, and 17 tests. The terminal chatbot uses LangChain create_agent with an explicitly configured OpenAI model, in-session history, a guarded simulated credit-purchase tool, read-only balance tool, stable per-order retry keys, and operator approval/rejection/resume/kill commands. Linked the sample and updated validation counts in root/sample READMEs and AI usage.
- Why: Demonstrate how a package consumer builds a conversational agent with SpendGuard enforcement, without giving the model approval authority or blocking chat while a purchase is held.
- Validation: Installed langchain-openai 1.7.0; `pip check` found no broken requirements (the earlier interrupted editable install still produces an invalid-distribution warning). Chatbot tests: 17 passed in 3.70s. Full suite: 113 passed in 13.75s. Tested real LangChain graphs with scripted local models, multi-turn context, allow/hold/deny, operator/external approval, rejection, kill/resume, retry protection, restart recovery through original order IDs, terminal flow, missing configuration, and redacted provider errors. CLI `--help`, documentation links, and diff whitespace checked. The initial history test reused one fake AIMessage ID; corrected the test fixture to supply distinct replies, matching normal model behavior.
- Limitations: Live OpenAI calls were not made; model availability and interactive dashboard behavior remain unverified. Purchases are simulated; model usage is not budgeted. Conversation/session mappings live in memory, while SQLite retains spending records. After restart, reissue the original order ID and quantity before approval/resume. Fixed sample policy is registered at startup; explicit `--reset` clears the selected database's requests and kill state. No runtime library or standalone package changes were needed. Human review pending; user `test.py` preserved; no remote push.

## 2026-10-11T03:20:47+05:30 — Add guarded LangChain tools

- Changed: Added optional `langchain` extra and `spendguard.integrations.langchain.wrap_tool`; persisted tool arguments/results with reservations and idempotency checks; deferred external approvals to the waiting/resumed wrapper instead of default mock adapters. Added 17 integration tests and `sample_app/langchain_agent.py`; updated core, sample, root, release, and AI documentation; synchronized 18 runtime files into `package_release/`.
- Why: Let LangChain agents execute paid tools under existing limits, approval, and kill controls while retaining a dependency-free core and independently installable package folder.
- Validation: Installed LangChain 1.4.4; full pytest passed, 96 tests in 10.82s, including an actual create_agent graph with a scripted model, concurrent calls, retries, denial, external approval, reject/expiry/kill, failure, and ainvoke. Ran offline agent example successfully without API keys or payments. Built standalone wheel, checked all 18 runtime files against source and snapshot, optional-only dependency metadata, core import with site-packages disabled, documentation links, and diff whitespace. `pip check` found no broken requirements, with a leftover invalid-distribution warning from the interrupted editable reinstall.
- Limitations: Supports synchronous StructuredTool tools with Pydantic schemas; native async-only tools, injected runtime/state, custom BaseTool subclasses, and streaming output are outside this version. Declared tool costs only; no inference-cost tracking or actual-cost reconciliation. Approved calls need the waiting/resumed wrapper; crash/partial external side effects still require manual reconciliation. Ordinary custom-executor approvals and previously reviewed adapter/dashboard/CLI findings remain unresolved. Interactive dashboard and real provider integration were not run. Local editable reinstall attempted twice but failed because Windows locks `spendguard.exe`; LangChain installed separately and module/example/tests worked. Human review pending; no index publication or remote push.

## 2026-10-11T02:52:36+05:30 — Assemble standalone package directory

- Changed: Added `package_release/` containing only `pyproject.toml`, a package-focused README, and the 16 library/fixture files under `spendguard/`. Retained runtime extras and removed the development-only extra from the release metadata. Linked the snapshot in the root README.
- Why: Supply an independently installable/buildable directory with only the files needed to distribute the package, excluding tests, sample apps, development records, environments, databases, and credentials.
- Validation: All 16 copied files matched the working library by SHA-256. `pip wheel ./package_release --no-deps --wheel-dir .pytest_cache/package-release-validation` succeeded after retrying outside the sandbox for temporary-file access. Inspected the wheel to verify every source/fixture byte, dashboard JSON, optional-only dependencies, and absence of tests, samples, databases, and bytecode. Removed build-generated folders from the package snapshot. No application or test rerun was needed because runtime sources are byte-identical to the previously tested library.
- Limitations: This is a separate snapshot; later library changes must be copied before rebuilding. Existing review findings remain unchanged. No index publication or separate source-archive build was performed; licensing metadata has not been selected by the project owner. User `test.py` remains untouched.

## 2026-10-11T02:44:12+05:30 — Explain standalone package consumption

- Changed: Reworked `sample_app/README.md` to run from the consumer directory with its own environment and a normal SpendGuard dependency installation; documented copying the app outside the repository, future index installation, direct API use, and adapter ownership. Linked the standalone workflow in the root README.
- Why: Clarify the user's intended example: how another developer consumes the installed package in their own application.
- Validation: Reviewed paths and consistency with the existing sample script; Git diff whitespace check. No additional installation, sample execution, or tests performed for this documentation-only clarification.
- Limitations: Package index publication is not verified. Independent installation and interactive demo remain unverified; mock-payment and executor configuration limitations are documented.

## 2026-10-11T02:39:53+05:30 — Add sample package consumer

- Changed: Added `sample_app/main.py` and its README showing public package imports, agent/policy setup, allow/hold/deny purchases, idempotent retries, budget reporting, and optional polling while approving through the dashboard. Linked the sample in the root README.
- Why: Provide a dedicated directory demonstrating how an application can use SpendGuard with isolated sample state.
- Validation: Reviewed source and instructions; `.\.venv\Scripts\python.exe -m py_compile sample_app/main.py` completed successfully and `git diff --check` found no whitespace errors. No sample application or interactive dashboard run was performed in this task.
- Limitations: Default adapters are mocks; background explanations may be interrupted when the sample exits. Existing source-review findings remain unresolved. The user's untracked `test.py` was left untouched.

## 2026-10-11T02:32:00+05:30 — Run full test suite

- Changed: Updated README, core documentation, and AI usage with the first full runtime test result; no application or test code changed.
- Why: Fulfill the user's request to run tests and replace pending-validation claims with observed results.
- Validation: `.\.venv\Scripts\python.exe -m pytest -q` initially reported 32 passed and 47 setup errors because the sandbox blocked pytest temporary directory creation. The authorized rerun outside the sandbox completed with **79 passed in 10.14s** and exit code 0 on Python 3.14.3.
- Limitations: Interactive dashboard/demo and release packaging not checked. The four preceding source-review findings remain unresolved; passing existing tests does not validate those uncovered cases.

## 2026-10-11T02:29:48+05:30 — Install local development environment

- Changed: Created ignored `.venv` with Python 3.14.3 and installed editable SpendGuard 0.1.0 with development extras; updated README, core documentation, and AI usage with actual setup status.
- Why: Complete the user's installation request and prepare the checkout for later application and test execution.
- Validation: `python -m venv .venv` and `.\.venv\Scripts\python.exe -m pip install -e ".[dev]"` completed after sandbox restrictions required elevated execution. `.\.venv\Scripts\python.exe -m pip check` reported `No broken requirements found.` Installed pytest 9.1.1, Streamlit 1.65.0, and OpenAI 3.28.0.
- Limitations: Application, tests, and import smoke checks were not run. Dependency consistency does not verify runtime compatibility or resolve the preceding source-review findings. The environment is local and ignored by Git.

## 2026-10-10T23:35:31+05:30 — Migrate backend to library core

- Changed: Moved policy, budget, storage, models, lifecycle code, and documentation into `spendguard/` and `docs/core.md`; added public dataclasses/errors/constants, package metadata, and guard tests. Removed obsolete owned server/auth files and requirements. Trimmed the environment example and updated setup documentation.
- Why: Implement the attached Person A library migration, retaining pure policy and atomic reservation logic while exposing the frozen `SpendGuard` API with no required runtime dependencies.
- Validation: Read-only source, Git status, and diff review; `git diff --check` reported no whitespace errors. No installation, imports, application, tests, or builds run, as requested. Added thread/process concurrency, idempotency, lifecycle, asynchronous callback, and shared-database tests for later execution.
- Limitations: Runtime and package installation unverified; teammate CLI/dashboard/tools absent. Existing incompatible database schemas are refused without clearing data. Reset refuses active execution; crash reconciliation remains manual. README setup changes follow repository documentation requirements. A pre-existing credential in the environment example was preserved in ignored local configuration and removed from the example; rotation was recommended after it appeared in tool output.

## 2026-10-10T22:33:31+05:30 — Author SpendGuard backend

- Changed: Added `gateway/{__init__,main,models,db,policy,budget,auth}.py`, backend tests, shared requirements, environment example, pytest configuration, and backend documentation. Extended Git ignores and updated README and AI usage.
- Why: Implement Person A's backend contract for deterministic spend enforcement and integration with Person B/C modules.
- Validation: Read the task, repository rules, and source changes; inspected Git status and diff. Application, tests, imports, builds, and installation were deliberately not run, per user instruction. No passing runtime result is claimed.
- Limitations: Runtime and integration verification pending; fallback executor is a mock; no recovery for interrupted execution. Reset returns 409 during execution. README received only backend setup/status updates required by the repository guide despite attachment ownership guidance.

Entry template:

```text
## <actual timestamp> — <short change title>

- Changed: <feature or files changed>
- Why: <reason for the change>
- Validation: <commands or manual checks actually run, with results>
- Limitations: <known issues or "None identified in these checks">
```

## Template setup — 10 October 2026

- Changed: Added the event README, rules, agent guide, change log, AI usage record, submission checklist, Git ignore rules, and pull request checklist.
- Why: Give participants a consistent starting point for event rules, basic coding patterns, documented changes, and regular commits.
- Validation: Checked local Markdown links, event detail consistency, required documents, and diff whitespace before publishing.
- Limitations: Documentation scaffolding only; no participant project, application, or working demo is included. GitHub publication and template status are verified separately after creation.
