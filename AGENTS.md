# Agent Playbook

Purpose-built instructions for code-focused agents working inside `github.com/wenga/poe_trade`.
This repo is currently planning-heavy with markdown, expects future Python modules/scripts for Path of Exile tooling, and relies on ClickHouse for storage.

## Repo Context
- Path of Exile tooling goal: ingest trade data, support pricing heuristics, and surface Leagues/Items for downstream automation.
- ClickHouse backend hosts historical item snapshots; schema changes go through explicit migrations and queries run against a read-optimized store.
- Python-first development now drives new features; assume the repo root will eventually have packages such as `poe_trade` and `poe_trade.cli` once contributors add them.
- Keep opencode hooks and any listed `.opencode/rules/*.md` guidance in mind when editing docs or code.

## Principles
1. **Speed with proof**: report the commands run plus their output or explain why a run was skipped; never claim completion without evidence.
2. **Scope discipline**: focus on one concern per edit, keep context limited to relevant files, and avoid dragging unrelated directories into the change.
3. **Safety & security**: never log secrets, treat ClickHouse queries as production data contracts, and add negative-path coverage when you change authentication or config flow.

## Command Recipes (Python workflow patterns)
> Repo currently lacks a formal Python package layout; treat the commands below as the templates to apply once `poe_trade` packages or scripts land.

- Create/activate virtualenv (assumes Python 3.11+ installed):
  ```
  python -m venv .venv
  source .venv/bin/activate
  ```
- Install dependencies (add `requirements.txt` once it exists or install locally defined extras):
  ```
  pip install --upgrade pip
  pip install -r requirements.txt  # or replace with internal deps when the file is added
  ```
- Run linters/formatters (ruff is preferred; add `ruff.toml` when configured):
  ```
  ruff check path/to/module  # restrict to touched modules
  ```
- Optional static typing (run once mypy config appears):
  ```
  mypy poe_trade  # narrow to directories you changed, drop once config exists
  ```
- Test suite with pytest (use markers or module paths once tests exist):
  ```
  pytest tests/  # swap for targeted `tests/unit/test_item.py` when you edit that area
  ```
- Run application CLI or script (replace with actual entry points later):
  ```
  python -m poe_trade.cli --help  # substitute real module when created
  ```
- Capture command outputs and paste-critical sections into your final note to satisfy the proof requirement.

## ClickHouse Schema & Query Safety
- Always author additive migrations; never drop columns or tables without a staged data-mirroring plan.
- Avoid `ALTER TABLE ... DELETE` or other destructive DDL in production. If a cleanup is unavoidable, document the manual approval path and include explicit `NOTE` comments in migrations.
- Test query changes locally with `clickhouse-local` or a dev ClickHouse cluster before proposing schema tweaks.
- Clearly state migration intent in PR descriptions: mention the target table, affected columns, and whether the change is backward-compatible.
- Annotate any script that writes to ClickHouse with a warning comment and link to the migration plan (e.g., `# migration: add future_index to poe.trade_snapshots`).

## Documentation & Evidence Discipline
- Keep doc style concise and instruction-driven; follow the terse tone already in `AGENTS.md` and related HOWTOs.
- When referencing commands, specify exact modules/paths that currently exist; note when referenced files (e.g., future Python modules) are placeholders.
- Include minimal but sufficient evidence for assertions: paste the relevant command output snippet or explain why you could not capture it.
- Treat this file as the authoritative runbook; if you update other docs, mention the change in your summary so future agents know where to look for instructions.

## Working Tree Hygiene, Commit & PR Guidance
- Assume you may land in a dirty worktree; run `git status` before editing so you know what is already changed.
- Do not stage or revert files you did not touch unless the user explicitly asks for it.
- Never amend existing commits; only create commits when the user asks, and keep them scoped and descriptive.
- When preparing a PR summary, focus on the “why,” cite the commands you ran, and list any remaining manual follow-up (tests, migrations, docs).

## Uncertainty Handling & Next Steps Checklist
- If requirements are unclear, search the repo for similar patterns before asking; document any assumptions in your final note.
- Only ask follow-up questions when a missing detail materially affects the outcome or involves secrets/production changes.
- Next steps checklist:
  1. Confirm targeted Python commands completed (or note why not).
  2. Record ClickHouse migration intent and safety notes with the change.
  3. Suggest 1-2 logical follow-ups (tests, docs, automation) as numbered options in your reply so the user can pick one.
