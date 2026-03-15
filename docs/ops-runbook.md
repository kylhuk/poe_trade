# Operations Runbook

## Launch checks
- Confirm `.env` contains the ClickHouse credentials plus `POE_OAUTH_CLIENT_ID`/`POE_OAUTH_CLIENT_SECRET_FILE` (or `POE_OAUTH_CLIENT_SECRET`). Without OAuth the collectors stall immediately.
- If `POE_ENABLE_CXAPI=true`, also confirm `POE_OAUTH_SCOPE` includes `service:cxapi` before starting the daemon.
- Run `docker compose config` to validate the clickhouse + schema_migrator + market_harvester topology.
- `make up` to build and launch ClickHouse, schema_migrator, and market_harvester.
- `poe-migrate --status` before starting the collectors to guarantee no pending schema changes, then run `poe-migrate --apply` once ClickHouse is healthy.
- After services start, `docker compose exec clickhouse clickhouse-client --query "SELECT 1"` to verify connectivity, and check `poe_ingest_status` for the newest `market_harvester` heartbeats.

## Monitoring & SLOs
- `poe_trade.bronze_ingest_checkpoints` is the canonical queue-cursor log; watch `queue_key`, `feed_kind`, `cursor_hash`, `status`, and `retrieved_at` to diagnose drift.
- The `StatusReporter` entries in `poe_trade.poe_ingest_status` include `queue_key`, `feed_kind`, `stalled_since`, and `error_count` for the latest daemon health view.
- `topOpportunities` on the dashboard are sourced from scanner recommendations; `criticalAlerts` remain message-derived diagnostics only.
- `poe_trade.bronze_requests` is the single source for rate-limit telemetry; repeated 429s or `retry_after_seconds` spikes show where the API is throttling the harvester.
- ClickHouse health matters: use `system.metrics`/`system.events` plus the `clickhouse-client` query above to catch authentication or resource pressure before ingestion fails.

## Failure recovery
1. **Stale ingestion:** restart `market_harvester`, verify `poe_ingest_status` shows a new `last_ingest_at`, and confirm the relevant `queue_key` in `poe_trade.bronze_ingest_checkpoints` advances before resuming downstream analytics.
2. **Checkpoint drift:** identify the cursor with the stale timestamp, inspect the `bronze_ingest_checkpoints` error column, and only reset or rewind the cursor after confirming the replayed snapshot matches the missing range.
3. **Rate-limit storms (429s):** rotate OAuth secrets, increase `POE_RATE_LIMIT_BACKOFF_MAX`, or add jitter; the offending queue/realm pair is logged in `poe_trade.bronze_requests` and on the `market_harvester` logs.
4. **ClickHouse connection failures:** ensure `CH_USER`/`CH_PASSWORD` (or the `POE_*` aliases) match the configured credentials, confirm the database exists via `CREATE DATABASE IF NOT EXISTS poe_trade`, and check `clickhouse-server` logs for `Memory limit exceeded` or `too many connections` errors.
5. **Escalation:** when multiple collectors show lag or rate-limit alerts, capture `docker compose logs` for `market_harvester` and `clickhouse`, archive the `poe_trade.bronze_ingest_checkpoints` output, and notify the team with the findings plus the command history.

## Penalty tiles & stale data
- `v_slo_metrics.ingest_latency_seconds` and `v_slo_metrics.alert_latency_seconds` drive the penalty tiles; any measurement above the 60s/30s targets should be treated as a service-level loss of availability.
- The `PoeNinjaSnapshotScheduler` caches responses for up to 180 seconds; if a league stays in `stale=true` territory for longer, trigger the fallback drill described in `docs/evidence/ops-automation/README.md`.
- Alert when `poe_trade.poe_ingest_status` shows `status` containing `rate_limited` for more than a minute—use that as a cue to inspect `poe_trade.bronze_requests` rather than hammering the API.

## Reference commands
- `curl -i http://127.0.0.1:8080/healthz` for unauthenticated API health checks.
- `curl -i -H "Authorization: Bearer $POE_API_OPERATOR_TOKEN" -H "Origin: https://app.example.com" http://127.0.0.1:8080/api/v1/ops/contract` to bootstrap frontend-facing route and capability metadata.
- `curl -i -H "Authorization: Bearer $POE_API_OPERATOR_TOKEN" -H "Origin: https://app.example.com" http://127.0.0.1:8080/api/v1/ops/services` for visible service inventory and allowed lifecycle actions.
- `curl -i -H "Authorization: Bearer $POE_API_OPERATOR_TOKEN" "http://127.0.0.1:8080/api/v1/ops/scanner/recommendations?sort=liquidity_score&limit=5&min_confidence=0.8"` to inspect rich opportunity contract fields (semanticKey, searchHint, itemName, etc.).
- `curl -i -X POST -H "Authorization: Bearer $POE_API_OPERATOR_TOKEN" -H "Origin: https://app.example.com" http://127.0.0.1:8080/api/v1/actions/services/market_harvester/restart` to trigger the only supported lifecycle control path.
- `curl -i -H "Authorization: Bearer $POE_API_OPERATOR_TOKEN" -H "Origin: https://app.example.com" "http://127.0.0.1:8080/api/v1/stash/tabs?league=Mirage&realm=pc"` to verify stash endpoint status (`feature_unavailable` is expected until stash backend rollout completes).
- `poe-ledger-cli service --name market_harvester` to launch the market sync daemon through the CLI router and inherit the shared logging configuration.
- `poe-ledger-cli service --name market_harvester -- --once --dry-run` to run one queue cycle without writing ClickHouse rows.
- `poe-ledger-cli sync status` to inspect the latest queue status rows when ClickHouse is reachable.
- `poe-ledger-cli sync psapi-once` and `poe-ledger-cli sync cxapi-backfill --hours 168` to run one-shot feed-specific sync cycles.
- `poe-ledger-cli refresh gold --group refs --dry-run` to list the active gold refresh SQL assets.
- `poe-ledger-cli strategy list`, `poe-ledger-cli strategy enable bulk_essence`, and `poe-ledger-cli strategy disable bulk_essence` to inspect and control strategy-pack availability.
- `poe-ledger-cli research backtest --strategy bulk_essence --league Mirage --days 14` to print `run_id\tstrategy_id\tleague\tlookback_days\tstatus\topportunity_count\texpected_profit_chaos\texpected_roi\tconfidence\tsummary`; `no_data` means no source rows for the window, `no_opportunities` means source rows existed but strategy rows did not.
- `poe-ledger-cli research backtest-all --league Mirage --days 14 --enabled-only` to print one summary row per enabled strategy with the same status contract.
- `poe-ledger-cli scan once --league Mirage --dry-run` and `poe-ledger-cli scan watch --league Mirage --max-runs 2 --dry-run` to exercise recommendation runs.
- `poe-ledger-cli journal buy --strategy bulk_essence --league Mirage --item-or-market-key sample --price-chaos 100 --quantity 20 --dry-run` (CLI-only) to test manual journal writes.
- `poe-ledger-cli alerts list` (diagnostics/messages), `poe-ledger-cli alerts ack --id <alert_id>`, and `poe-ledger-cli report daily --league Mirage` to inspect operator output tables.

- `poe-migrate --dry-run --apply` for migrations; the runner stores state in `poe_trade.poe_schema_migrations`, so reruns are safe.
- `clickhouse-client --query "SELECT * FROM poe_trade.bronze_ingest_checkpoints ORDER BY retrieved_at DESC LIMIT 5"` for the freshest checkpoint metadata.
- `clickhouse-client --query "SELECT status, count() FROM poe_trade.research_backtest_summary GROUP BY status ORDER BY status"` to verify typed backtest summary outcomes.
