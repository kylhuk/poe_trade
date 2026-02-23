# Public stash ingestion gap

## Current state

- `poe_trade/ingestion/market_harvester.py` runs the harvest loop (realms × leagues), reads/writes the `CheckpointStore`, forwards `next_change_id` as the `id` query param, and streams every stash payload into `poe_trade.raw_public_stash_pages` while reporting status.
- `poe_trade/ingestion/poe_client.py` forms HTTP calls, honors `RateLimitPolicy`, retries with exponential backoff/jitter, and treats a 429 as a trigger to sleep before the next attempt.
- `poe_trade/services/market_harvester.py` wires the hunter with configuration, rate-limit policy, ClickHouse client, checkpoints, OAuth, and exposes `--league/--realm/--interval/--dry-run/--once` CLI switches.
- `poe_trade/config/constants.py` currently defaults `poe_api_base_url` to `https://api.pathofexile.com`, matching the official host that `settings.get_settings()` surfaces for every harvester caller.
- `poe_trade/cli.py` exposes `poe-ledger-cli service --name market_harvester …` as the documented operator entrypoint.

## Requirement alignment matrix

| Requirement | Current coverage | Status |
|-------------|------------------|--------|
| Official base URL (`https://api.pathofexile.com`) | `DEFAULT_POE_API_BASE_URL` is set to `https://api.pathofexile.com`, and `settings.get_settings()` plus every harvester client source that constant before building requests, so the official host is the default. | Implemented (default official host). |
| next_change_id loop & checkpointing | `MarketHarvester._harvest` reads `CheckpointStore`, passes the last cursor as `id`, validates payload shape (`next_change_id` + `stashes`), and refuses checkpoint advancement on stale cursor (`next_change_id == cursor`) while reporting `stale cursor`. | Implemented (validated cursor loop with stale no-op guard). |
| Rate-limit/backoff + 429 behavior | `PoeClient`/`RateLimitPolicy` compute Retry-After, exponential backoff with jitter, honor `Retry-After` headers, and limit retries to `cfg.rate_limit_max_retries`. | Implemented (per file reference). |
| Deterministic emission/idempotency expectations | Ingested rows include `checkpoint`, `next_change_id`, and `stash_id`; stale cursor requests now skip emission entirely, and `_rows_from_payload` deduplicates repeated non-empty stash IDs inside a single payload before insert. | Implemented (no stale re-emits + payload-level stash dedup). |
| CLI entrypoint/operator usability | `poe_trade/services/market_harvester.py` creates the CLI service, enforces OAuth precheck with explicit env guidance, and `poe_trade/cli.py` exposes it via the `service` subcommand with flag forwarding. | Implemented (service now fails fast with actionable credential guidance). |

## Failure-handling expectations

- **429 handling**: `PoeClient` honors `Retry-After` first and then falls back to bounded exponential backoff via `RateLimitPolicy`; terminal failures bubble as runtime errors to the harvester, which keeps the checkpoint frozen and reports error state through `StatusReporter`.
- **Network errors & timeouts**: retryable network failures (for example `URLError`) flow through the same bounded retry path and preserve cursor/checkpoint on terminal failure; harvester status surfaces the failure through `status="error"`, `error_count`, and `stalled_since` fields.
- **Malformed payloads**: payloads missing required fields (`next_change_id`, `stashes`) are rejected, logged as failures, and do not emit rows or advance the checkpoint.

### Acceptance+evidence checklist

- 429 handling: `pytest tests/unit/test_poe_client.py -k 429` verifies Retry-After-aware retry behavior in the client layer.
- Network/runtime failures: `pytest tests/unit/test_market_harvester.py -k upstream` verifies frozen checkpoint, no writes, and error status reporting for runtime and network exceptions.
- Malformed payloads: `pytest tests/unit/test_market_harvester.py -k malformed` verifies invalid payloads are rejected with no writes and unchanged checkpoint state.

## Minimal follow-on hardening (non-blocking)

1. Add request-level emission metadata only if downstream consumers require stronger replay provenance than the current `checkpoint` + `next_change_id` + `stash_id` envelope.
1. Extend integration coverage to exercise live OAuth token expiry/refresh churn against long-running harvester loops.
1. Add operator quick-reference snippets (common `poe-ledger-cli service --name market_harvester` combinations) to runbooks for faster onboarding.

## Risks & data-contract notes (additive only)

- `poe_trade.raw_public_stash_pages` is append-only; adding deterministic emission metadata must avoid rewriting existing rows and should only append new columns or audit tables so ClickHouse readers retain backwards compatibility.
- Base URL default is now aligned to `https://api.pathofexile.com`; operators can still override `POE_API_BASE_URL` for controlled migrations or backfill experiments.
- Any checkpoint-change logic must not delete stored cursors: keep the file-backed checkpoints append-only, and ensure new validation merely raises/logs errors without removing existing checkpoint files.
