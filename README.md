# Wraeclast Ledger — Market Sync Engine

## Purpose
- Ingest Path of Exile market data into ClickHouse, keep schema migrations current, and run the CLI-first market sync daemon.

## Bootstrap
1. `python -m venv .venv`
2. `source .venv/bin/activate`
3. `cp .env.example .env` and adjust the ClickHouse, OAuth, realm, and polling values for your environment.
4. `.venv/bin/pip install -e .`
5. `python -m poe_trade.cli --help` to inspect the CLI router and available service names.
6. `docker compose config` to validate the ClickHouse + ingestion topology.
7. `make up` to start ClickHouse, schema_migrator, and market_harvester in one command.

## After Docker is running
- `docker compose ps` to confirm the core services are healthy.
- `docker compose logs --follow clickhouse schema_migrator market_harvester` to tail the ingestion logs.
- `docker compose exec clickhouse clickhouse-client --query "SELECT 1"` to verify ClickHouse accepts connections.
- `make down` to stop every container while keeping the ClickHouse data volume intact for the next `make up`.
- Refer to `docs/ops-runbook.md` for queue-based telemetry, checkpoint history, and failure patterns.

## ML Quick Start (Mirage)
1. `.venv/bin/poe-ml train-loop --league Mirage --dataset-table poe_trade.ml_price_dataset_v1 --model-dir artifacts/ml/mirage_v1 --max-iterations 2 --max-wall-clock-seconds 1800 --no-improvement-patience 2 --min-mdape-improvement 0.005`
2. `.venv/bin/poe-ml status --league Mirage --run latest`
3. `.venv/bin/poe-ml report --league Mirage --model-dir artifacts/ml/mirage_v1 --output artifacts/ml/mirage_v1/latest-report.json`
4. `.venv/bin/poe-ml predict-one --league Mirage --input-format poe-clipboard --stdin < tests/fixtures/ml/sample_clipboard_item.txt`

ML verdict vocabulary:
- `promote`: candidate beats incumbent on MDAPE improvement, coverage floor, and protected cohort checks.
- `hold`: candidate fails one or more promotion checks.
- `stopped_no_improvement`: train-loop stopped because candidate-vs-incumbent deltas stayed below patience policy.
- `stopped_budget`: train-loop stopped because iteration or wall-clock budget was exhausted.

## Protected API Foundation
The API service now exposes authenticated ML, Ops read models, and guarded service actions.
Set these exact env vars before starting the API service:
- `POE_API_BIND_HOST` (default `127.0.0.1`)
- `POE_API_BIND_PORT` (default `8080`)
- `POE_API_OPERATOR_TOKEN` (required)
- `POE_API_CORS_ORIGINS` (comma-separated allowlist, for example `https://app.example.com`)
- `POE_API_MAX_BODY_BYTES` (default `32768`)
- `POE_API_LEAGUE_ALLOWLIST` (default `Mirage`)

Start the service:
- `POE_API_OPERATOR_TOKEN=phase1-token POE_API_CORS_ORIGINS=https://app.example.com .venv/bin/python -m poe_trade.cli service --name api -- --host 127.0.0.1 --port 8080`

Verify routes:
- `curl -i http://127.0.0.1:8080/healthz`
- `curl -i -H "Authorization: Bearer phase1-token" -H "Origin: https://app.example.com" http://127.0.0.1:8080/api/v1/ops/contract`
- `curl -i -H "Authorization: Bearer phase1-token" -H "Origin: https://app.example.com" http://127.0.0.1:8080/api/v1/ops/services`
- `curl -i -H "Authorization: Bearer phase1-token" -H "Origin: https://app.example.com" http://127.0.0.1:8080/api/v1/ops/messages`
- `curl -i -X POST -H "Authorization: Bearer phase1-token" -H "Origin: https://app.example.com" http://127.0.0.1:8080/api/v1/actions/services/market_harvester/restart`
- `curl -i -H "Authorization: Bearer phase1-token" -H "Origin: https://app.example.com" http://127.0.0.1:8080/api/v1/ml/contract`
- `curl -i -H "Authorization: Bearer phase1-token" -H "Origin: https://app.example.com" http://127.0.0.1:8080/api/v1/ml/leagues/Mirage/status`
- `curl -i -X POST -H "Authorization: Bearer phase1-token" -H "Content-Type: application/json" --data '{"input_format":"poe-clipboard","payload":"Item Class: Maps\nRarity: Rare\nGrim Veil\nCemetery Map","output_mode":"json"}' http://127.0.0.1:8080/api/v1/ml/leagues/Mirage/predict-one`
- `curl -i -X POST -H "Authorization: Bearer phase1-token" -H "Content-Type: application/json" --data '{"itemText":"Item Class: Maps\nRarity: Rare\nGrim Veil\nCemetery Map"}' http://127.0.0.1:8080/api/v1/ops/leagues/Mirage/price-check`
- `curl -i -H "Authorization: Bearer phase1-token" -H "Origin: https://app.example.com" "http://127.0.0.1:8080/api/v1/stash/tabs?league=Mirage&realm=pc"`
- `curl -i -H "Authorization: Bearer phase1-token" -H "Origin: https://evil.example.com" http://127.0.0.1:8080/api/v1/ml/leagues/Mirage/status`

Current non-goals:
- no browser-direct long-lived operator-token storage model
- no lifecycle controls for one-shot jobs (`schema_migrator`, ad-hoc `poe-ml` commands)
- no API self-stop/self-restart action for the serving `api` process
- no wildcard CORS policy
- no in-app TLS termination

## Frontend local dev
- Install deps: `cd frontend && npm install`
- Run Vite: `npm run dev` (binds to `http://127.0.0.1:5173`)
- Vite proxies `/api` and `/healthz` to `http://127.0.0.1:8080` by default.

## CLI surface
- `.venv/bin/python -m poe_trade.cli service --name market_harvester -- --help` to see the market sync daemon arguments and polling knobs.
- `market_harvester --realm <name> --once` runs one daemon cycle directly if you prefer bypassing the CLI router.
- When `POE_ENABLE_CXAPI=true`, the same daemon cycle also syncs the latest completed Currency Exchange hour for each configured realm.
- `.venv/bin/python -m poe_trade.cli sync psapi-once` runs one PSAPI-only cycle, and `.venv/bin/python -m poe_trade.cli sync cxapi-backfill --hours 168` runs one CX-only cycle.
- `.venv/bin/python -m poe_trade.cli refresh gold --group refs --dry-run` lists the current gold refresh SQL assets.
- `.venv/bin/python -m poe_trade.cli strategy list` shows discovered strategy packs; `strategy enable <id>` and `strategy disable <id>` toggle `enabled = ...` in each `strategy.toml`.
- `.venv/bin/python -m poe_trade.cli research backtest --strategy bulk_essence --league Mirage --days 14` prints `run_id\tstrategy_id\tleague\tlookback_days\tstatus\topportunity_count\texpected_profit_chaos\texpected_roi\tconfidence\tsummary` with explicit `completed`, `no_data`, `no_opportunities`, or `failed` status.
- `.venv/bin/python -m poe_trade.cli research backtest-all --league Mirage --days 14 --enabled-only` prints one summary row per enabled strategy using the same canonical header.
- `make backtest-all BACKTEST_LEAGUE=Mirage BACKTEST_DAYS=14` runs one command that backtests every discovered strategy pack (omit `BACKTEST_FLAGS` for real writes, or add `BACKTEST_FLAGS=--dry-run` for a safe preflight).
- `.venv/bin/poe-ml train-loop --league Mirage --dataset-table poe_trade.ml_price_dataset_v1 --model-dir artifacts/ml/mirage_v1 --max-iterations 2 --max-wall-clock-seconds 1800 --no-improvement-patience 2 --min-mdape-improvement 0.005` runs a bounded rebuild/train/evaluate loop and returns explicit stop reason.
- `.venv/bin/poe-ml status --league Mirage --run latest` prints candidate-vs-incumbent verdict, deltas, stop reason, route hotspots, and active model version.
- `.venv/bin/poe-ml report --league Mirage --model-dir artifacts/ml/mirage_v1 --output artifacts/ml/mirage_v1/latest-report.json` writes route metrics, hotspot summaries, outlier cleaning summary, and low-confidence reasons.
- `.venv/bin/poe-ml predict-one --league Mirage --input-format poe-clipboard --stdin < tests/fixtures/ml/sample_clipboard_item.txt` prints routed interval pricing with confidence and sale probability percentages.
- `.venv/bin/python -m poe_trade.cli scan once --league Mirage --dry-run` and `.venv/bin/python -m poe_trade.cli scan watch --league Mirage --max-runs 2 --dry-run` exercise the recommendation pipeline.
- `.venv/bin/python -m poe_trade.cli scan plan --league Mirage --limit 20` runs one scan and prints actionable `strategy_id`, `search_hint`, `buy_plan`, `max_buy`, `exit_plan`, and confidence fields for quick execution.
- `.venv/bin/python -m poe_trade.cli journal buy ...`, `.venv/bin/python -m poe_trade.cli alerts list`, and `.venv/bin/python -m poe_trade.cli report daily --league Mirage` cover the manual truth loop and operator reports.
- `poe-migrate --status --dry-run` shows pending schema changes, and `poe-migrate --apply` applies new `schema/migrations` from the repo.
- `clickhouse-client --query "SELECT status, count() FROM poe_trade.research_backtest_summary GROUP BY status ORDER BY status"` verifies typed backtest statuses in storage.

## Sanity queries
- `clickhouse-client --multiquery < schema/sanity/bronze.sql` validates the newest ingest batches.
- `clickhouse-client --multiquery < schema/sanity/silver.sql` verifies downstream coverage for derived views.
- `clickhouse-client --multiquery < schema/sanity/gold.sql` checks the current gold reference marts.
- Use `clickhouse-client --query "SELECT max(retrieved_at) FROM poe_trade.bronze_ingest_checkpoints"` to see how fresh the checkpoints are.

## Troubleshooting
- **Stale ingestion:** query `poe_ingest_status` and `bronze_ingest_checkpoints`; restart the stalled `market_harvester` only after verifying the queue cursor and the latest request history are sane.
- **Rate limit backoff:** inspect `poe_trade.bronze_requests` for 429s, rotate OAuth secrets (`POE_OAUTH_CLIENT_ID`, `POE_OAUTH_CLIENT_SECRET_FILE`) if the upstream service keeps throttling, and confirm `market_harvester` respect the `POE_RATE_LIMIT_*` settings.
- **Checkpoint lag alarms:** `StatusReporter` writes `stalled_since` details; the dashboard (see `docs/ops-runbook.md`) surfaces amber/red states when `bronze_ingest_checkpoints` timestamps drift.
- **ClickHouse auth failures:** align `CH_USER`/`CH_PASSWORD` (or their `POE_*` aliases) with the stored credentials in the existing volume—ClickHouse does not reinitialize users when the data directory is reused.
## Environment variables
- `POE_CLICKHOUSE_URL`, `POE_CLICKHOUSE_DATABASE`, `POE_CLICKHOUSE_USER`, `POE_CLICKHOUSE_PASSWORD` (alias `CH_*` supported).
- `POE_API_BASE_URL`, `POE_AUTH_BASE_URL`, `POE_USER_AGENT`, and the rate limit controls (`POE_RATE_LIMIT_*`).
- `POE_REALMS`, `POE_ENABLE_PSAPI`, `POE_ENABLE_CXAPI`, `POE_PSAPI_POLL_SECONDS`, and `POE_CXAPI_*` control queue-based market sync.
- `POE_OAUTH_CLIENT_ID`, `POE_OAUTH_CLIENT_SECRET` or `_FILE`, `POE_OAUTH_SCOPE`, and `POE_OAUTH_GRANT_TYPE` for the OAuth refresh path.
- `POE_API_BIND_HOST`, `POE_API_BIND_PORT`, `POE_API_OPERATOR_TOKEN`, `POE_API_CORS_ORIGINS`, `POE_API_MAX_BODY_BYTES`, and `POE_API_LEAGUE_ALLOWLIST` for the protected ML API service.
- Keep `POE_ENABLE_CXAPI=false` until the environment is ready for hourly Currency Exchange sync; when enabled, `POE_OAUTH_SCOPE` must include `service:cxapi`.
- `POE_CHECKPOINT_DIR`, `POE_CURSOR_DIR`, and `POE_LEAGUES` remain compatibility-only aliases; ClickHouse checkpoint history is the canonical cursor source.


## Schema migrations
1. `.venv/bin/pip install -e .` so `poe-migrate` registers alongside the ingestion services.
2. `poe-migrate --status --dry-run` to inspect pending migrations without mutating ClickHouse.
3. `poe-migrate --apply` once ClickHouse is reachable; migration progress is recorded in `poe_trade.poe_schema_migrations` so rerunning is safe.
