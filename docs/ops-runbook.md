# Operations Runbook

## Launch checks
- confirm `.env` secrets exist and `docker compose config` succeeds for ClickHouse, API, and UI profiles.
- ensure ClickHouse schema migrations report `0 pending` and the `poe_trade.poe_schema_migrations` table reflects the latest step.
- start the `ledger_api` service locally and verify `/healthz` plus `/v1/ops/dashboard` return expected payloads.

## Monitoring & SLOs
- **Public stash freshness:** target <= 10m lag (including upstream delay). `poe_trade.ops.slo.evaluate_ingest_freshness` drives the status shown on the dashboard and writes notes when the lag exceeds the goal.
- **Currency snapshot freshness:** target <= 65m lag; the same helper reports both streams so we can detect drift in one place.
- **Checkpoint drift:** each cursor should checkpoint within its `expected_interval_minutes`. `detect_checkpoint_drift` flags any drift that exceeds twice that cadence and powers the dashboard alert badge.
- **Rate-limit storms:** repeated 429/4xx counts over the most recent 30m window feed `detect_repeated_rate_errors`; 429 entries are marked as `critical` and surfaced in the dashboard alerts list.
- **Ops dashboard:** `/dashboard/internal/index.html` renders ingest rate, request rate, checkpoint health, lag/SLO status, and alert panels. The page falls back to static sample data when `/v1/ops/dashboard` is unreachable.

## Failure recovery
1. **Stale ingestion:** inspect the `poe_ingest_status` ClickHouse view (or equivalent logging) for stalled cursors, restart the corresponding collector service, and confirm the dashboard shows the timestamp advancing again.
2. **Checkpoint drift:** capture the cursor name from the dashboard, verify the last checkpoint in the `checkpoints` store, rerun the job that owns it, and only reset the cursor after ensuring replay is safe.
3. **429/4xx storms:** examine recent API call logs for repeated client errors, rotate API keys or add jitter if the upstream service is rate limiting, and confirm the alert clears in the following 30m window.
4. **Escalation:** if multiple panels alert simultaneously, notify the team with the dashboard snapshot plus the failing ingestion/endpoint logs and any ClickHouse query output clearing the forensics.
