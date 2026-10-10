# Change log

Record each meaningful project change during the event, newest first. Update this file in the same commit as the change. Use a real timestamp with timezone, for example `YYYY-MM-DDTHH:MM:SS+05:30`.

## Event build log

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
