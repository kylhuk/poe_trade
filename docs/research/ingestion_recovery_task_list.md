# Ingestion Recovery Checklist (Current)

## Objective
Keep the repository focused on ingestion and ClickHouse reliability.

## Current Scope
- Runtime: `clickhouse`, `schema_migrator`, `market_harvester`
- Lifecycle commands: `make up`, `make down`
- Active schema: ingestion/status/migration tables only

## Ongoing Checklist
1. Keep docs aligned with ingestion-only runtime.
2. Keep ClickHouse migrations additive by default.
3. Verify startup and teardown through `make up` / `make down`.
4. Track ingestion freshness through checkpoint/status queries.

## Safety Rules
- Do not reintroduce removed runtime surfaces without a dedicated plan and migration impact review.
- Do not use destructive ClickHouse schema changes unless explicitly approved.

## Sources
- `README.md`
- `docs/ops-runbook.md`
- `docs/research/ingestion_only_constraints.md`
