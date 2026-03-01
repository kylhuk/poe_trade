# PoE Trade Architecture (Ingestion Only)

## Services
- `clickhouse`
- `schema_migrator`
- `market_harvester`

## Data Flow
1. `market_harvester` fetches PoE public stash data.
2. Ingestion workers write append-only rows to ClickHouse bronze/status tables.
3. Checkpoint/status data tracks freshness and failure recovery.

## Active ClickHouse Tables
- `raw_public_stash_pages`
- `raw_account_stash_snapshot`
- `bronze_ingest_checkpoints`
- `bronze_trade_metadata`
- `bronze_requests`
- `poe_ingest_status`
- `poe_schema_migrations`

## Guardrails
- Treat schema changes as additive unless there is explicit approval.
- Never drop data in emergency recovery paths.
- Keep ingestion request pacing compatible with PoE API rate-limit headers.

## Lifecycle
- `make up` boots the ingestion stack.
- `make down` tears it down while preserving volumes.
