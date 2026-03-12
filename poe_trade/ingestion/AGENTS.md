# INGESTION GUIDE

## OVERVIEW

`poe_trade/ingestion/` owns external API traffic, checkpointing, rate-limit behavior, and ingest status telemetry.

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| OAuth + token refresh | `market_harvester.py` | `oauth_client_factory`, `OAuthClient`, `OAuthToken` |
| Upstream HTTP behavior | `poe_client.py` | Retry logic, headers, metadata wrappers |
| Backoff and pacing | `rate_limit.py` | `Retry-After` and dynamic rate-limit parsing |
| Cursor persistence | `sync_state.py` | ClickHouse-backed queue cursor lookup |
| Heartbeats / lag state | `status.py` | Writes ingest status rows |
| Secondary snapshots | `poeninja_snapshot.py` | Cache/TTL-driven poe.ninja fetches |

## CONVENTIONS

- Preserve upstream league/realm fields from API payloads; never invent synthetic realm or league values.
- Queue keys are feed/realm scoped; keep replay, idle-state, and stale-cursor behavior idempotent.
- Respect `Retry-After` and parsed rate-limit headers before issuing more requests.
- Keep request metadata and status writes audit-friendly; ops docs depend on those tables.
- When auth, rate-limit, or checkpoint behavior changes, add negative-path coverage in `tests/unit/`.

## ANTI-PATTERNS

- Do not tighten retry loops around 4xx/429 responses.
- Do not delete or silently rewind checkpoint state as part of normal recovery logic.
- Do not drop duplicate-page protection for stash IDs inside a single payload.
- Do not replace API-sourced league filtering with hard-coded defaults from config.

## VERIFICATION

```bash
.venv/bin/pytest tests/unit/test_market_harvester.py
.venv/bin/pytest tests/unit/test_market_harvester_auth.py
.venv/bin/pytest tests/unit/test_poe_client.py
.venv/bin/pytest tests/unit/test_rate_limit.py
```
