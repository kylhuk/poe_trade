---
description: PR readiness check + run fast validation commands (go test + lint if available).
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

Fast validation (best-effort)
- Go tests:
!`go test ./...`

- Go lint (if configured):
!`golangci-lint run`

Task
- Interpret the outputs (pass/fail) and propose next actions.
- Produce a PR description (summary, test instructions, risks).
- If proto files changed, remind to run buf lint/breaking/gen.

Keep output concise.
