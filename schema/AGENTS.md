# SCHEMA GUIDE

## OVERVIEW

`schema/` is the SQL contract surface for ClickHouse migrations and read-only sanity queries.

## STRUCTURE

```text
schema/
|- migrations/   # ordered SQL migrations, one file per version
`- sanity/       # read-only multiquery checks for bronze/silver/gold layers
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Add DDL | `migrations/*.sql` | Keep numeric ordering and additive evolution |
| Review current storage model | `migrations/*.sql` | Bronze/silver/gold, ops artifacts, grants, codecs |
| Verify freshness/coverage | `sanity/*.sql` | Bronze/silver/gold plus BuildAtlas sanity checks |
| Change migration execution rules | `../poe_trade/db/migrations.py` | Python runner for status/apply |

## CONVENTIONS

- New migrations use the next zero-padded version prefix and a descriptive snake_case label.
- Prefer additive ClickHouse changes: new tables, new columns, new views, new grants.
- Keep sanity SQL read-only and safe for operator spot checks.
- Document any compatibility-sensitive migration in the adjacent code/docs summary.

## ANTI-PATTERNS

- Do not reorder or rename old migration files.
- Do not hide destructive cleanup in routine migrations.
- Do not put data-writing side effects into `sanity/` queries.
- Do not assume multi-statement HTTP execution; the runner splits statements deliberately.

## VERIFICATION

```bash
poe-migrate --status --dry-run
clickhouse-client --multiquery < schema/sanity/bronze.sql
```
