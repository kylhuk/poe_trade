---
name: evidence-bundle
description: Produces a paste-ready verification bundle (commands + outputs) for reviews/PRs.
---
# Evidence bundle

Use this skill at the end of any task that changes code.

1. List changed files (group by area: code/tests/docs/migrations).

2. Provide commands + exact outputs you observed, in this order:
   - Formatter (e.g., `ruff format`, `python -m black`).
   - Lint (e.g., `ruff check`, `ruff lint`).
   - Tests (unit/integration, e.g., `pytest`).
   - Type checks or CLI smoke (e.g., `mypy poe_trade`, `python -m poe_trade.cli --help`).
   - ClickHouse/migration validation (SQL run via `clickhouse-local`, Dry-run migration, etc.).

3. If you could not run a command:
   - State WHY (tool missing, CI-only, permissions).
   - Mention how that affects your confidence in the change.
