# PACKAGE GUIDE

## OVERVIEW

`poe_trade/` is the shipped Python package: config, ClickHouse access, ingestion logic, and service entry points.

## STRUCTURE

```text
poe_trade/
|- config/       # env parsing, defaults, shared constants
|- db/           # ClickHouse client + migration runner
|- ingestion/    # harvester, clients, checkpoints, rate limits, status
`- services/     # CLI-facing service entry points
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Add CLI/service behavior | `cli.py`, `services/` | Router delegates to `poe_trade.services.*.main` |
| Change env handling | `config/settings.py` | Keep aliases and defaults backward-compatible |
| Change ClickHouse calls | `db/clickhouse.py`, `db/migrations.py` | Preserve additive data-contract expectations |
| Change ingest flow | `ingestion/` | Follow domain-specific rules in `ingestion/AGENTS.md` |
| Verify behavior | `../tests/unit/` | Tests mirror package modules |

## CONVENTIONS

- Use `logging`, not ad hoc prints.
- Read environment via `config.settings.get_settings()` unless a lower-level helper already owns the parsing.
- Keep public entry points thin: argument parsing in `services/`, business logic in `ingestion/` or `db/`.
- Preserve console-script names from `pyproject.toml`: `poe-ledger-cli`, `market_harvester`, `poe-migrate`.

## ANTI-PATTERNS

- Do not add new environment aliases without tests in `tests/unit/test_settings_aliases.py`.
- Do not bury service startup policy inside `cli.py`; route to `services/` modules.
- Do not couple `db/` to Path of Exile-specific parsing; keep data-source logic in `ingestion/`.

## VERIFICATION

```bash
.venv/bin/python -m poe_trade.cli --help
.venv/bin/pytest tests/unit
```
