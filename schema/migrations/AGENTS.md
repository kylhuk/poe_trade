# MIGRATIONS GUIDE

## OVERVIEW

`schema/migrations/` is the ordered DDL history for ClickHouse; each file is part of the compatibility contract applied by `poe-migrate`.

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Pick next version | Directory listing | Continue the zero-padded numeric sequence |
| Understand runner behavior | `../../poe_trade/db/migrations.py` | Status/apply logic, statement splitting, checksum tracking |
| Review prior ingest patterns | Recent `*_ingest_*.sql`, `*_metadata_*.sql`, `*_nullable_league.sql` files | Metadata, dedup, nullable-league evolution |
| Review ops patterns | `*_ops_*.sql`, `*_alerts.sql`, `*_fallback_drill_*.sql` files | Ops views, alerts, fallback drill artifacts |

## CONVENTIONS

- Keep one migration concern per file with a descriptive snake_case suffix.
- Preserve forward-only, additive evolution unless an explicit staged compatibility plan exists.
- Assume the runner executes split statements in order and records checksums in `poe_schema_migrations`.
- Mention downstream table/view impact in the accompanying code or docs summary.

## ANTI-PATTERNS

- Do not edit old migration contents after they have shipped.
- Do not combine sanity-query experimentation with migration DDL.
- Do not sneak destructive cleanup into a version that looks additive by name.

## VERIFICATION

```bash
poe-migrate --status --dry-run
```
