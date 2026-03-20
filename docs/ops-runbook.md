# Operations Runbook

## Launch checks
- Confirm `.env` contains the ClickHouse credentials plus `POE_OAUTH_CLIENT_ID`/`POE_OAUTH_CLIENT_SECRET_FILE` (or `POE_OAUTH_CLIENT_SECRET`). Without OAuth the collectors stall immediately.
- If `POE_ENABLE_CXAPI=true`, also confirm `POE_OAUTH_SCOPE` includes `service:cxapi` before starting the daemon.
- Run `docker compose config` to validate the clickhouse + schema_migrator + market_harvester topology.
- `make up` to build and launch ClickHouse, schema_migrator, and market_harvester.
- `poe-migrate --status` before starting the collectors to guarantee no pending schema changes, then run `poe-migrate --apply` once ClickHouse is healthy. Keep the new migration `schema/migrations/0044_poeninja_serving_profile_table_v1.sql` up to date so the serving profile table is created next time this workflow runs.
- After services start, `docker compose exec clickhouse clickhouse-client --query "SELECT 1"` to verify connectivity, and check `poe_ingest_status` for the newest `market_harvester` heartbeats.

## Monitoring & SLOs
- `poe_trade.bronze_ingest_checkpoints` is the canonical queue-cursor log; watch `queue_key`, `feed_kind`, `cursor_hash`, `status`, and `retrieved_at` to diagnose drift.
- The `StatusReporter` entries in `poe_trade.poe_ingest_status` include `queue_key`, `feed_kind`, `stalled_since`, and `error_count` for the latest daemon health view.
- `topOpportunities` on the dashboard are sourced from scanner recommendations; `criticalAlerts` remain message-derived diagnostics only.
- `goldDiagnostics` in the analytics report (via `/api/v1/ops/analytics/report`) provides per-mart freshness, row-counts, and league-visibility states.
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

## PoeNinja steady-state pipeline
- `poeninja_snapshot` now writes raw PoeNinja snapshots for incremental ClickHouse derivation; it no longer rebuilds the ML dataset in the default service loop.
- Confirm steady-state mode from `.sisyphus/state/poeninja_snapshot-last-run.json`; `snapshot_mode` should be `steady_state_snapshot_only` and `downstream_rebuild_triggered` should be `false` unless you explicitly ran a backfill.
- Verify raw snapshot freshness with `clickhouse-client --query "SELECT count(), max(sample_time_utc) FROM poe_trade.raw_poeninja_currency_overview WHERE league='Mirage'"`.
- Verify incremental FX freshness with `clickhouse-client --query "SELECT count(), max(hour_ts) FROM poe_trade.ml_fx_hour_v2 WHERE league='Mirage'"`.
- Verify incremental dataset growth with `clickhouse-client --query "SELECT count(), max(as_of_ts) FROM poe_trade.ml_price_dataset_v2 WHERE league='Mirage'"`.
- Use `poe-ledger-cli service --name poeninja_snapshot -- --once --league Mirage --full-rebuild-backfill` only for explicit repair/backfill work; this is not the steady-state path.

## Mod-rollup governance (32GB shared host)
- Baseline evidence must exist at `.sisyphus/evidence/task-1-baseline-shared-host.json` before any rollup cutover decision.
- Shadow parity evidence must exist at `.sisyphus/evidence/task-5-shadow-read.json`; strict-order diagnostics can be inspected at `.sisyphus/evidence/task-5-shadow-read-strict.json`.
- Fallback readiness evidence must exist at `.sisyphus/evidence/task-6-fallback-pass.json` and `.sisyphus/evidence/task-6-fallback-error.log`.
- Active ClickHouse guardrails for `poe_ingest` are verified from `.sisyphus/evidence/task-7-settings-active.txt` and must show `max_memory_usage=1610612736`, `max_threads=4`, `max_execution_time=180`, `max_bytes_before_external_group_by=268435456`, `max_bytes_before_external_sort=268435456`.
- Parity contract invariants now live in `poe_trade.qa_parity_contract`; run `PYTHONPATH=. python3 scripts/verify_parity_contract.py --output .sisyphus/evidence/task-1-parity-contract.json` to lock the documented keys/modes before cutover.
- Cutover gate file is `.sisyphus/evidence/task-10-cutover-gate.json`; rollout is blocked unless `cutover_approved=true`.

### Cutover command sequence
- `POE_CLICKHOUSE_URL=http://localhost:8123 POE_CLICKHOUSE_USER=default POE_CLICKHOUSE_PASSWORD='' PYTHONPATH=. .venv/bin/python -m poe_trade.db.migrations --status --dry-run`
- `PYTHONPATH=. python3 scripts/compare_mod_feature_paths.py --league Mirage --page-size 5000 --comparison-mode strict --output .sisyphus/evidence/task-3-dual-read-baseline.json`
- `PYTHONPATH=. python3 scripts/verify_mod_rollup_rollback.py --output .sisyphus/evidence/task-9-rollback-ready.json`
- `PYTHONPATH=. python3 scripts/evaluate_cutover_gate.py --baseline .sisyphus/evidence/task-1-baseline-shared-host.json --candidate .sisyphus/evidence/task-8-final-benchmark.json --shadow .sisyphus/evidence/task-5-shadow-read-strict.json --fallback .sisyphus/evidence/task-6-fallback-pass.json --settings .sisyphus/evidence/task-7-settings-active.txt --user-config config/clickhouse/users/poe.xml --output .sisyphus/evidence/task-10-cutover-gate.json`

### Cutover thresholds
- `parity_mismatch_count == 0`
- `candidate_memory_mean <= 1610612736`
- `read_bytes_reduction >= 0.30`
- `duration_reduction >= 0.20`

### Fallback and rollback trigger
- Trigger immediate fallback when any cutover threshold fails or when `.sisyphus/evidence/task-10-cutover-gate.json` contains `cutover_approved=false`.
- Force legacy bounded path by exporting `POE_ML_MOD_ROLLUP_FORCE_LEGACY=true` and keeping `POE_ML_MOD_FEATURE_FALLBACK_PAGE_SIZE_CAP=1000`.
- Disable rollup primary mode by exporting `POE_ML_MOD_ROLLUP_PRIMARY_ENABLED=false`.
- Re-verify rollback readiness with `PYTHONPATH=. python3 scripts/verify_mod_rollup_rollback.py --output .sisyphus/evidence/task-9-rollback-ready.json`.

### Fast-sale shadow gate controls
- Shadow duration minimum: `7` days and `10000` scored items before cutover eligibility.
- Require `3` consecutive passing windows for serving-path metrics before enabling cutover.
- Roll back when any threshold is breached:
  - protected-cohort extreme miss worsening `> 15%`,
  - confidence calibration ECE degradation `> 0.03`,
  - abstain-rate spike `> 25%` without error improvement.

## Reference commands
- `curl -i http://127.0.0.1:8080/healthz` for unauthenticated API health checks.
- `curl -i -H "Authorization: Bearer $POE_API_OPERATOR_TOKEN" -H "Origin: https://poe.lama-lan.ch" http://127.0.0.1:8080/api/v1/ops/contract` to bootstrap frontend-facing route and capability metadata.
- `curl -i -H "Authorization: Bearer $POE_API_OPERATOR_TOKEN" -H "Origin: https://poe.lama-lan.ch" http://127.0.0.1:8080/api/v1/ops/services` for visible service inventory and allowed lifecycle actions.
- `curl -i -H "Authorization: Bearer $POE_API_OPERATOR_TOKEN" "http://127.0.0.1:8080/api/v1/ops/scanner/recommendations?sort=liquidity_score&limit=5&min_confidence=0.8"` to inspect rich opportunity contract fields (semanticKey, searchHint, itemName, mlInfluenceScore, effectiveConfidence, etc.).
- `curl -i -X POST -H "Authorization: Bearer $POE_API_OPERATOR_TOKEN" -H "Origin: https://poe.lama-lan.ch" http://127.0.0.1:8080/api/v1/actions/services/market_harvester/restart` to trigger the only supported lifecycle control path.
- `curl -i -H "Authorization: Bearer $POE_API_OPERATOR_TOKEN" -H "Origin: https://poe.lama-lan.ch" "http://127.0.0.1:8080/api/v1/stash/status?league=Mirage&realm=pc"` to verify stash gate state; when `POE_ENABLE_ACCOUNT_STASH=false`, the payload returns `status=feature_unavailable` with `featureFlag=POE_ENABLE_ACCOUNT_STASH` and a remediation `reason`.
- `curl -i -H "Authorization: Bearer $POE_API_OPERATOR_TOKEN" -H "Origin: https://poe.lama-lan.ch" "http://127.0.0.1:8080/api/v1/stash/tabs?league=Mirage&realm=pc"` to verify tab retrieval; this route returns HTTP 503 `feature_unavailable` while `POE_ENABLE_ACCOUNT_STASH=false`.
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

## Mod-rollup backfill and cutover runbook
- Chunked backfill: `PYTHONPATH=. python3 scripts/run_mod_feature_backfill.py --run-id <run-id> --league Mirage --chunk-size 5000` drives `ml_item_mod_feature_states_v1` in bounded offsets while checkpoint rows track chunk progress.
- Monitor progress and resumable recovery: `PYTHONPATH=. python3 scripts/monitor_mod_feature_backfill.py --run-id <run-id>` prints completed/running/failed chunk counts and, with `--auto-resume`, re-invokes the runner from the first stuck chunk.
- Guardrail proof: `PYTHONPATH=. python3 scripts/check_mod_feature_settings.py` writes `.sisyphus/evidence/task-7-settings-active.txt` that must show `ml_heavy` values `max_memory_usage=1610612736`, `max_threads=4`, `max_execution_time=180`, `max_bytes_before_external_group_by=268435456`, and `max_bytes_before_external_sort=268435456` while `config/clickhouse/users/poe.xml` keeps `<max_concurrent_queries>1</max_concurrent_queries>`.
- Rollback checklist: `PYTHONPATH=. python3 scripts/verify_mod_rollup_rollback.py --output .sisyphus/evidence/task-9-rollback-ready.json` verifies required migrations, shadow evidence, fallback proof, and helper scripts before cutover.
- Cutover gate command: `PYTHONPATH=. python3 scripts/evaluate_cutover_gate.py --candidate <candidate-metrics.json> --baseline .sisyphus/evidence/task-1-baseline-shared-host.json --shadow .sisyphus/evidence/task-5-shadow-read-strict.json --fallback .sisyphus/evidence/task-6-fallback-pass.json --settings .sisyphus/evidence/task-7-settings-active.txt --output .sisyphus/evidence/task-10-cutover-gate.json` enforces zero mismatches, <=1.5 GiB p95 memory, >=30% read-bytes reduction, >=20% p95 duration drop, strict shadow mode, and guardrail compliance.
- Final release decision: `PYTHONPATH=. python3 scripts/final_release_gate.py --cutover-gate .sisyphus/evidence/task-10-cutover-gate.json --rollback-ready .sisyphus/evidence/task-9-rollback-ready.json --runbook-check .sisyphus/evidence/task-11-runbook-check.txt --parity-log .sisyphus/evidence/task-2-parity-order.log --service-regression-log .sisyphus/evidence/task-8-cadence.log --output .sisyphus/evidence/task-12-final-release-gate.json` summarizes parity, memory, rollback, and documentation readiness into a single approve/reject artifact.
