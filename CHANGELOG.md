# Change log

Record each meaningful project change during the event, newest first. Update this file in the same commit as the change. Use a real timestamp with timezone, for example `YYYY-MM-DDTHH:MM:SS+05:30`.

## Event build log

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
