# TEST GUIDE

## OVERVIEW

`tests/` holds the executable verification surface for package modules, with current coverage concentrated in `tests/unit/`.

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Harvester flow | `unit/test_market_harvester.py` | Main behavior matrix and helpers |
| Queue sync state | `unit/test_sync_state.py` | ClickHouse-backed cursor lookup and failure handling |
| OAuth refresh behavior | `unit/test_market_harvester_auth.py` | Token caching and refresh paths |
| Service entry points | `unit/test_market_harvester_service.py`, `unit/test_service_registry.py` | CLI/service wiring |
| Config aliases | `unit/test_settings_aliases.py` | `CH_*`, `POE_CURSOR_DIR`, OAuth secret file handling |
| ClickHouse migration runner | `unit/test_migrations.py` | SQL splitting and apply/status behavior |
| Client backoff and pacing | `unit/test_poe_client.py`, `unit/test_rate_limit.py` | Retries, metadata, dynamic pacing |

## CONVENTIONS

- Use `pytest` discovery with focused module paths for touched areas.
- Keep test doubles local and explicit; `tests/unit/__init__.py` already provides lightweight stubs for optional dependencies.
- Mirror behavior changes with negative-path assertions when auth, networking, rate limits, or config parsing changes.
- Prefer deterministic fixtures/helpers over external services or real network calls.

## ANTI-PATTERNS

- Do not add live ClickHouse or HTTP dependencies to unit tests.
- Do not add new config/env behavior without updating alias coverage.
- Do not hide important setup in global state when a helper factory can keep tests isolated.

## VERIFICATION

```bash
.venv/bin/pytest tests/unit
```
