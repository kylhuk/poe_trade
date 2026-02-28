# PoE Trade Ingestion Overview

Date: 2026-02-28

## Scope
This repository is now ingestion-only. It keeps the minimum stack needed to collect Path of Exile trade data and store it in ClickHouse.

## Runtime Components
- `clickhouse`
- `schema_migrator`
- `market_harvester`
- `stash_scribe` (optional)

## Data Contracts
The active ClickHouse contract is limited to:
- `poe_schema_migrations`
- `raw_public_stash_pages`
- `raw_account_stash_snapshot`
- `bronze_ingest_checkpoints`
- `bronze_trade_metadata`
- `bronze_requests`
- `poe_ingest_status`

## Operations
- Start services: `make up`
- Stop services: `make down`

## Notes
- Historical UI/API/analytics surfaces have been retired from runtime.
- Schema work must remain additive by default.
