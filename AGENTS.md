# PROJECT KNOWLEDGE BASE

**Generated:** 2026-03-10T19:53:14+01:00
**Commit:** 212ffea
**Branch:** main

## OVERVIEW

Path of Exile ledger repo for ClickHouse-backed ingestion, schema migrations, and operator runbooks.
The live implementation is a Python 3.11 package in `poe_trade/`; root markdown files are useful context but may lag shipped code.

## STRUCTURE

```text
poe_trade/
|- poe_trade/              # Python package: config, db, ingestion, services
|- schema/                 # ClickHouse migrations + sanity queries
|- docs/                   # Ops runbooks, requirements, research, evidence
|- tests/unit/             # Unit coverage for config, db, ingestion, services
|- config/clickhouse/      # ClickHouse server overrides used by local runtime
|- dashboard/internal/     # Lightweight UI assets
`- *.md                    # Architecture, backlog, and planning context
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Bootstrap local env | `README.md` | Canonical setup, docker, CLI, and migration commands |
| Run services | `poe_trade/cli.py`, `poe_trade/services/` | `poe-ledger-cli`, `market_harvester`, `poe-migrate` |
| Change ingestion logic | `poe_trade/ingestion/` | Checkpoints, rate limits, OAuth, metadata fetches |
| Change ClickHouse access | `poe_trade/db/`, `schema/` | Python client plus SQL migration tree |
| Update ops docs | `docs/ops-runbook.md`, `docs/evidence/` | Keep commands and tables aligned with code |
| Add tests | `tests/unit/` | Mirror touched module, keep negative paths covered |

## CODE MAP

| Symbol | Type | Location | Role |
|--------|------|----------|------|
| `main` | function | `poe_trade/cli.py` | CLI router for service entry points |
| `Settings` | dataclass | `poe_trade/config/settings.py` | Environment-backed runtime config |
| `ClickHouseClient` | class | `poe_trade/db/clickhouse.py` | HTTP client for ClickHouse queries |
| `MigrationRunner` | class | `poe_trade/db/migrations.py` | Loads, statuses, and applies numbered SQL migrations |
| `MarketHarvester` | class | `poe_trade/ingestion/market_harvester.py` | Public stash ingest loop and checkpoint flow |
| `StatusReporter` | class | `poe_trade/ingestion/status.py` | Writes operational ingest status |

## CONVENTIONS

- Python floor is `>=3.11`; install locally with `.venv/bin/pip install -e .`.
- Prefer command-first evidence: quote the exact command you ran and the key output.
- Route runtime config through `poe_trade.config.settings`; `CH_*` aliases are supported, while checkpoint-dir aliases are compatibility-only and no longer define canonical cursor storage.
- Local orchestration is `docker compose` plus `make up` / `make down`; migrations use `poe-migrate`.
- Treat root planning docs as context only. For behavior, prefer `README.md`, package code, `schema/`, and `docs/ops-runbook.md`.

## ANTI-PATTERNS (THIS PROJECT)

- Never claim build/test/CLI success without output or an explicit `not run` note.
- Never log secrets or copy OAuth credentials into docs, tests, fixtures, or examples.
- Never make destructive ClickHouse changes (`DROP`, column reorder, mass delete) without an explicit staged plan.
- Never revert unrelated dirty-worktree files; inspect `git status` first and leave foreign edits alone.
- Never document planned commands as if they already exist.

## UNIQUE STYLES

- Docs stay terse, operational, and evidence-backed.
- Path of Exile terms stay precise: league, realm, stash, checkpoint, snapshot, trade metadata.
- Ops docs name concrete tables/views (`bronze_ingest_checkpoints`, `bronze_requests`, `poe_ingest_status`) instead of generic dashboards.

## COMMANDS

```bash
python3 -m venv .venv
source .venv/bin/activate
.venv/bin/pip install -e .
.venv/bin/python -m poe_trade.cli --help
.venv/bin/pytest tests/unit
docker compose config
make up
make down
poe-migrate --status --dry-run
poe-migrate --apply
clickhouse-client --multiquery < schema/sanity/bronze.sql
```

## NOTES

- `python` is not on PATH in this environment; use `python3` or `.venv/bin/python`.
- The old root playbook described the package layout as future work; that is stale now.
- Child `AGENTS.md` files should only add local rules, never restate root safety policy.
