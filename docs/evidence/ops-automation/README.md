# Ops automation evidence

## SLO penalty tile contract
- the dashboard reads the latest rows from `v_slo_metrics` so the tile reflects live values for `ingest_latency_seconds` and `alert_latency_seconds`.
- ingest latency must stay at or below **60s**; alert latency must stay at or below **30s**.  Any excess becomes a penalty bucket that operators investigate using the Failure recovery checklist.

## Fallback drill workflow
- trigger fallback drills with the `fallback-drill` CLI (run `fallback-drill --help` for the latest switches) and choose a league/item or service to exercise offline handling.
- each drill should write a new row to `fallback_drill_log`, capturing the triggered league, status, and timestamps so auditors can replay the incident.
- after the drill completes, keep the log entry until downstream consumers confirm baseline snapshots are restored.

## Verification commands
- `pytest tests/unit/test_ops_dashboard_service.py` → **15 passed**, 13 deselected (ops dashboard tests passed).
- `pytest tests/unit/test_fallback_drill.py` → **2 passed** (fallback drill tests passed).
- `fallback-drill --help` runs successfully (fallback drill CLI `--help` available).

## Screenshots
- N/A (headless environment)
