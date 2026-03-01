# Wraeclast Ledger — Ingestion Pack

## Purpose
- Ingest Path of Exile marketplace data into ClickHouse, keep the schema migrations current, and expose a lightweight CLI for the public stash collector.

## Bootstrap
1. `python -m venv .venv`
2. `source .venv/bin/activate`
3. `cp .env.example .env` and adjust the ClickHouse, OAuth, and league/realm values for your environment.
4. `.venv/bin/pip install -e .`
5. `python -m poe_trade.cli --help` to inspect the CLI router and available service names.
6. `docker compose config` to validate the ClickHouse + ingestion topology.
7. `make up` to start ClickHouse, schema_migrator, and market_harvester in one command.

## After Docker is running
- `docker compose ps` to confirm the core services are healthy.
- `docker compose logs --follow clickhouse schema_migrator market_harvester` to tail the ingestion logs.
- `docker compose exec clickhouse clickhouse-client --query "SELECT 1"` to verify ClickHouse accepts connections.
- `make down` to stop every container while keeping the ClickHouse data volume intact for the next `make up`.
- Refer to `docs/ops-runbook.md` for ingestion-focused dashboards, checkpoints, and failure patterns.

## CLI surface
- `.venv/bin/python -m poe_trade.cli service --name market_harvester -- --help` to see the harvester-specific arguments and polling knobs.
- `market_harvester --league <name> --realm <name>` runs the collector directly if you prefer bypassing the CLI router.
- `poe-migrate --status --dry-run` shows pending schema changes, and `poe-migrate --apply` applies new `schema/migrations` from the repo.

## Sanity queries
- `clickhouse-client --multiquery < schema/sanity/bronze.sql` validates the newest ingest batches.
- `clickhouse-client --multiquery < schema/sanity/silver.sql` verifies downstream coverage for derived views.
- Use `clickhouse-client --query "SELECT max(retrieved_at) FROM poe_trade.bronze_ingest_checkpoints"` to see how fresh the checkpoints are.

## Troubleshooting
- **Stale ingestion:** query the `poe_ingest_status` and `bronze_ingest_checkpoints` tables; restart the stalled `market_harvester` or replay the cursor only after verifying the snapshot is safe.
- **Rate limit backoff:** inspect `poe_trade.bronze_requests` for 429s, rotate OAuth secrets (`POE_OAUTH_CLIENT_ID`, `POE_OAUTH_CLIENT_SECRET_FILE`) if the upstream service keeps throttling, and confirm `market_harvester` respect the `POE_RATE_LIMIT_*` settings.
- **Checkpoint lag alarms:** `StatusReporter` writes `stalled_since` details; the dashboard (see `docs/ops-runbook.md`) surfaces amber/red states when `bronze_ingest_checkpoints` timestamps drift.
- **ClickHouse auth failures:** align `CH_USER`/`CH_PASSWORD` (or their `POE_*` aliases) with the stored credentials in the existing volume—ClickHouse does not reinitialize users when the data directory is reused.
## Environment variables
- `POE_CLICKHOUSE_URL`, `POE_CLICKHOUSE_DATABASE`, `POE_CLICKHOUSE_USER`, `POE_CLICKHOUSE_PASSWORD` (alias `CH_*` supported).
- `POE_CHECKPOINT_DIR` / `POE_CURSOR_DIR` for persistence of per-queue cursors.
- `POE_API_BASE_URL`, `POE_AUTH_BASE_URL`, `POE_USER_AGENT`, and the rate limit controls (`POE_RATE_LIMIT_*`).
- `POE_REALMS`, `POE_LEAGUES`, and `POE_STASH_API_PATH` scope the public ingest.
- `POE_OAUTH_CLIENT_ID`, `POE_OAUTH_CLIENT_SECRET` or `_FILE`, `POE_OAUTH_SCOPE`, and `POE_OAUTH_GRANT_TYPE` for the OAuth refresh path.


## Schema migrations
1. `.venv/bin/pip install -e .` so `poe-migrate` registers alongside the ingestion services.
2. `poe-migrate --status --dry-run` to inspect pending migrations without mutating ClickHouse.
3. `poe-migrate --apply` once ClickHouse is reachable; migration progress is recorded in `poe_trade.poe_schema_migrations` so rerunning is safe.
