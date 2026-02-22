---
description: PR readiness check + PR summary (no auto-running tests).
agent: proj-lead
subtask: true
---

Context (git)
- Status:
!`git status --porcelain=v1`

- Changed files:
!`git diff --name-only`

- Diff summary:
!`git diff --stat`

Task
1) Identify scope and user-visible behavior changes.
2) Identify risk areas (security, protocol wire-compat, concurrency, migrations).
3) List the exact commands that SHOULD be run before merge (tests, lint, buf checks) based on what changed.
4) Produce a PR description:
   - Summary (3–6 bullets)
   - What changed (grouped)
   - How to test
   - Notes/risks
5) Call out missing tests/docs explicitly.

Keep output concise.
