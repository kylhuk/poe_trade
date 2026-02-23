# Wraeclast Ledger — Markdown Pack

Files:
- 00-ecosystem-overview.md — tool names, integration contracts, repo layout
- 01-architecture.md — Docker + ClickHouse architecture and table tiers
- 02-implementation-tasklist.md — epics and definitions of done
- 03-strategy-registry.md — community-sourced strategies to validate with your data
- 04-exilelens-linux-item-capture.md — Linux clipboard/OCR client tool
- 05-buildatlas-pob-intelligence.md — BuildAtlas: autonomous build discovery + build coach (PoB-powered)
- 06-db-etl-roadmap.md — Detailed database/ETL roadmap prioritizing PoE ingestion

## Bootstrap
1. `python -m venv .venv` (or your preferred virtualenv manager);
2. `source .venv/bin/activate` to enter the environment;
3. `cp .env.example .env` and adjust values for your local environment;
4. `pip install -e .` to install the package and scripts; the `poe-ledger-cli` script becomes available;
5. `python -m poe_trade.cli --help` to inspect the service router CLI;
6. `python -m poe_trade.cli service --name market_harvester --help` to view per-service flags;
7. `docker compose config` to validate the multi-service topology (core + optional profiles);
8. `docker compose up --build` to spin up ClickHouse with the ledger API/UI services (optionally add `--profile optional`).

## Environment variables
- Prefer `POE_*` variables in `.env`; compatibility aliases (`CH_*`, `POE_CURSOR_DIR`) are supported for legacy runbooks.
- Core values: `POE_CLICKHOUSE_URL`, `POE_CLICKHOUSE_DATABASE`, `POE_CLICKHOUSE_USER`, `POE_CLICKHOUSE_PASSWORD`, `POE_CHECKPOINT_DIR`, `POE_USER_AGENT`, `POE_LEAGUES`, `POE_REALMS`.
- OAuth credentials are required only for services that call private PoE APIs (`stash_scribe`, optionally authenticated `market_harvester`): set `POE_OAUTH_CLIENT_ID` and provide the client secret through `POE_OAUTH_CLIENT_SECRET_FILE` (preferred) or `POE_OAUTH_CLIENT_SECRET`; the default grant is `POE_OAUTH_GRANT_TYPE=client_credentials` with scope `POE_OAUTH_SCOPE=service:psapi`.
- ExileLens trigger protection: set `POE_STASH_TRIGGER_TOKEN` when enabling manual stash trigger endpoints.


## Schema migrations
1. Install the package (`pip install -e .`) so the `poe-migrate` script registers alongside the existing service runners.
2. Run `poe-migrate --status --dry-run` or `python -m poe_trade.db.migrations --status --dry-run` to inspect pending migrations without touching ClickHouse.
3. Apply pending migrations with `poe-migrate --apply` once ClickHouse is reachable; the runner stores progress in `poe_trade.poe_schema_migrations` and skips already applied steps.

## Sanity queries
- Use `clickhouse-client --multiquery < schema/sanity/bronze.sql` to validate bronze ingestion freshness.
- Use `clickhouse-client --multiquery < schema/sanity/silver.sql` for canonical coverage checks and `schema/sanity/gold.sql` for analytics health.
- Run `clickhouse-client --multiquery < schema/sanity/buildatlas.sql` when Atlas tables are populated to ensure the genome/eval tables respond before exposing them to the UI.

## ExileLens local client

### Requirements
- Linux desktop with at least one clipboard helper (`wl-paste`/`wl-copy` on Wayland, `xclip` or `xsel` for X11) and one screenshot helper (`grim` preferred, `maim` or `gnome-screenshot` as a fallback).
- `tesseract` for OCR fallback plus the usual Python dependencies (`poe_trade` install via `pip install -e .`).

### One-shot capture
- Ensure PoE copies text to the system clipboard (Ctrl+C or Ctrl+Alt+C) and run `python -m poe_trade.services.exilelens --endpoint http://localhost/v1/item/analyze --mode clipboard` to POST the payload.
- Force OCR capture by passing `--mode ocr --roi x,y,width,height` and rely on `grim`/`maim` plus `tesseract` to return the parsed text.
- Use `--league`/`--realm` if you need to pin the analyze context and `--debug-history` when you want the base64 screenshot stored in history for troubleshooting.

### Watch mode
- Use `python -m poe_trade.services.exilelens --watch-clipboard` to keep polling the clipboard (`--poll-interval` defaults to 0.4s) and automatically post a detect-worthy PoE item.
- Cap the runtime with `--max-events N` or interrupt with Ctrl+C once the desired number of captures fires.

### Clipboard copy helpers
- `--copy-field {est_chaos,list_fast,list_normal,list_patient}` copies the requested price value into the clipboard after a successful analyze (uses the same adapter that reads the clipboard, so the write path cascades through the available tool).
- Continue to use `--clipboard-text` and `--ocr-text` when running unit tests or reproducing a failure without touching the real clipboard.
