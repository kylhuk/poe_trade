# Endpoint map for BuildAtlas, Farming ROI, Flip Scanner, and stash backfill
| Feature | Route(s) | Service / Host | Port | Source |
| --- | --- | --- | --- | --- |
| BuildAtlas | `GET /v1/atlas/builds`<br>`GET /v1/builds/search`<br>`GET /v1/atlas/builds/{build_id}`<br>`GET /v1/builds/{build_id}`<br>`GET /v1/atlas/builds/{build_id}/export`<br>`GET /v1/builds/{build_id}/export`<br>`POST /v1/atlas/runs`<br>`POST /v1/atlas/coach/plan` | ledger_api FastAPI | 8000 (docker compose maps 8000:8000) | `poe_trade/api/app.py`: lines 135-186 |
| Farming ROI | `GET /v1/sessions/leaderboard` | ledger_api FastAPI | 8000 | `poe_trade/api/app.py`: lines 110-124 |
| Flip Scanner | `GET /v1/flips`<br>`GET /v1/flips/top` | ledger_api FastAPI | 8000 | `poe_trade/api/app.py`: lines 90-98 |
| Stash backfill | `POST /trigger` (on stash_scribe trigger server) | stash_scribe trigger server (starts via `StashScribe.start_trigger_server`) | user-provided `--trigger-port` (no default) | `poe_trade/ingestion/stash_scribe.py`: lines 252-268 |

> **Notes:** `stash_scribe`, `atlas_*`, and `llm_advisor` are behind the `optional` profile; enable them with `COMPOSE_PROFILES=optional` or `docker compose --profile optional`. `POE_STASH_TRIGGER_TOKEN` must be non-empty to keep `/trigger` callable, and the stored token is checked via the `X-Trigger-Token` header.
