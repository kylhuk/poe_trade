Title: Ingestion recovery state

Purpose: record the final ingestion-only scope after the runtime simplification.

Current state:
- Kept: `market_harvester`, ClickHouse, schema migrator, and CLI wrappers.
- Removed from runtime: non-ingestion surfaces and generated legacy artifacts.

Operational baseline:
- `make up` starts the stack.
- `make down` stops the stack.
- Rollback strategy stays additive for ClickHouse schema changes.
