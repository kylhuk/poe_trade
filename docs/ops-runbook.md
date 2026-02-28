# Operations Runbook

## Launch checks
- Confirm `.env` contains the ClickHouse credentials plus `POE_OAUTH_CLIENT_ID`/`POE_OAUTH_CLIENT_SECRET_FILE` (or `POE_OAUTH_CLIENT_SECRET`). Without OAuth the collectors stall immediately.
- Run `docker compose config` to validate the clickhouse + schema_migrator + market_harvester topology; add `stash_scribe` when you need private capture support.
- `make up` to build and launch ClickHouse, schema_migrator, market_harvester, and the optional `stash_scribe` profile.
- `poe-migrate --status` before starting the collectors to guarantee no pending schema changes, then run `poe-migrate --apply` once ClickHouse is healthy.
- After services start, `docker compose exec clickhouse clickhouse-client --query "SELECT 1"` to verify connectivity, and check `poe_ingest_status` for the newest `market_harvester`/`stash_scribe` heartbeats.

## Monitoring & SLOs
- `v_ops_ingest_health` mirrors the latest rows from `poe_trade.bronze_ingest_checkpoints`; amber/red levels correspond to checkpoint lag thresholds (amber >= 20s, red >= 60s).
- `poe_trade.bronze_ingest_checkpoints` records every crawl attempt; watch `cursor_hash`, `status`, and `retrieved_at` to diagnose drift.
- The `StatusReporter` entries in `poe_trade.poe_ingest_status` include `stalled_since` and `error_count`, which mirror the ingest health tiles described above.
- `poe_trade.bronze_requests` is the single source for rate-limit telemetry; repeated 429s or `retry_after_seconds` spikes show where the API is throttling the harvester or stash scribe.
- ClickHouse health matters: use `system.metrics`/`system.events` plus the `clickhouse-client` query above to catch authentication or resource pressure before ingestion fails.

## Failure recovery
1. **Stale ingestion:** restart the affected collector (`market_harvester` or `stash_scribe`), verify `poe_ingest_status` shows a new `last_ingest_at`, and ensure the checkpoint file under `POE_CHECKPOINT_DIR` advances before resuming downstream analytics.
2. **Checkpoint drift:** identify the cursor with the stale timestamp, inspect the `bronze_ingest_checkpoints` error column, and only reset or rewind the cursor after confirming the replayed snapshot matches the missing range.
3. **Rate-limit storms (429s):** rotate OAuth secrets, increase `POE_RATE_LIMIT_BACKOFF_MAX`, or add jitter; the offending league/realm pair is logged in `poe_trade.bronze_requests` and on the `market_harvester` logs.
4. **ClickHouse connection failures:** ensure `CH_USER`/`CH_PASSWORD` (or the `POE_*` aliases) match the configured credentials, confirm the database exists via `CREATE DATABASE IF NOT EXISTS poe_trade`, and check `clickhouse-server` logs for `Memory limit exceeded` or `too many connections` errors.
5. **Escalation:** when multiple collectors show lag or rate-limit alerts, capture `docker compose logs` for `market_harvester`, `stash_scribe`, and `clickhouse`, archive the `poe_trade.bronze_ingest_checkpoints` output, and notify the team with the findings plus the command history.

## Penalty tiles & stale data
- `v_slo_metrics.ingest_latency_seconds` and `v_slo_metrics.alert_latency_seconds` drive the penalty tiles; any measurement above the 60s/30s targets should be treated as a service-level loss of availability.
- The `PoeNinjaSnapshotScheduler` caches responses for up to 180 seconds; if a league stays in `stale=true` territory for longer, trigger the fallback drill described in `docs/evidence/ops-automation/README.md`.
- Alert when `poe_trade.poe_ingest_status` shows `status` containing `rate_limited` for more than a minute—use that as a cue to inspect `poe_trade.bronze_requests` rather than hammering the API.

## Reference commands
- `poe-ledger-cli service --name market_harvester` to launch the harvester through the CLI router and inherit the shared logging configuration.
- `poe-ledger-cli service --name stash_scribe` with `--trigger-port` to expose the manual stash capture endpoint.
- `poe-migrate --dry-run --apply` for migrations; the runner stores state in `poe_trade.poe_schema_migrations`, so reruns are safe.
- `clickhouse-client --query "SELECT * FROM poe_trade.bronze_ingest_checkpoints ORDER BY retrieved_at DESC LIMIT 5"` for the freshest checkpoint metadata.
