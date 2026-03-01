# Ingestion-only constraints research

Focus on ingesting Path of Exile market snapshots via `market_harvester` and landing the stream into ClickHouse; do not alter other workflows. Assume OAuth 2.1 credentials are available for service scopes, that the ingest CLI lives inside `poe_trade/ingestion`, and that ClickHouse tables such as `poe_trade.raw_account_stash_snapshot` already exist and must evolve safely.

## Source table
| Source | URL | Accessed | Trust level | Notes |
| --- | --- | --- | --- | --- |
| Path of Exile Developer Docs (overview + policies + rate-limit contract) | https://www.pathofexile.com/developer/docs | 2026-02-25 | High (GGG official docs) | Covers OAuth 2.1, client types, scopes, user-agent requirements, third-party policy notice, error codes, and the full `X-Rate-Limit-*` header contract that all public endpoints expose. |
| API Reference (Public Stashes / Account Stashes sections) | https://www.pathofexile.com/developer/docs/reference | 2026-02-25 | High (GGG official API reference) | Lists `/public-stash-tabs` flows (optional `realm`, cursor `id`, `next_change_id` semantics, 5-minute delivery delay) and private stash/cursor endpoints gated by `account:stashes`. |
| PoE Terms of Use & Privacy Policy (7b/7c/7i) | https://www.pathofexile.com/legal/terms-of-use-and-privacy-policy | 2026-02-25 | High (GGG legal site) | Clause 7 forbids unapproved scraping; clause 6/7/9 cover macro/automation compliance for non-API tooling, so ingestion must stay within documented endpoints. |
| ClickHouse Schema Changes Propagation Support (ClickPipes for MySQL) | https://clickhouse.com/docs/integrations/clickpipes/mysql/schema-changes | 2026-02-25 | High (ClickHouse documentation) | Confirms that only additive schema changes (e.g., `ALTER TABLE ADD COLUMN` appended to the end) propagate automatically; dropping/reordering columns breaks replication and must be avoided. |

## Constraints by topic (with applicability notes)

### Authorization & allowed scopes
- OAuth 2.1 is mandatory for almost every endpoint; confidential clients (our preferred mode) keep credentials secret, can request `service:psapi`, and issue long-lived tokens, whereas public clients are limited to Authorization Code + PKCE, cannot request `service:*` scopes, and share rate limits. The CLI must keep `POE_OAUTH_CLIENT_ID/SECRET` secret, rotate tokens before 28-day expiry, and include the `User-Agent: OAuth {...}` header so GGG can identify the app [Doc: Developer Docs].
  - `market_harvester` (`poe_trade/ingestion/market_harvester.py`) wires an optional `OAuthClient`; on token refresh it sets the bearer header before hitting `public-stash-tabs`, so ensure `service:psapi` scope and refresh logic remain aligned with `OAuthToken`'s 30-second safety window.
  - `market_harvester` uses `OAuthClient` when OAuth is configured to request `constants.DEFAULT_POE_STASH_API_PATH`; keep the `client_credentials` grant type + `service:psapi` scope enforced in `oauth_client_factory` (it already raises if the scope is missing). Treat access/refresh tokens as secrets and never emit them outside the CLI.
  - ClickHouse ingestion does not need additional auth, but downstream consumers rely on trustworthy metadata; keep the ingestion user agent and OAuth contract so the stream never breaks and we can map records back to the official API policies.

### Public stash API semantics
- `/public-stash-tabs` accepts optional `realm` (pc/xbox/sony) and `id` (cursor from `next_change_id`) and always returns `next_change_id` plus `stashes`. Empty `stashes` means “up-to-date”, and a 5-minute delay is noted before new data surfaces, so the harvester should expect burstless polling and avoid tight loops that ignore the documented lag [Doc: API Reference].
  - `market_harvester` already records `cursor`/`next_change_id` and skips writing if the cursor is unchanged; continue using `CheckpointStore` to persist these cursors so polling resumes exactly where PoE expects it.
  - `market_harvester` hits the public stash path (`constants.DEFAULT_POE_STASH_API_PATH`) and flushes snapshots into `poe_trade.raw_account_stash_snapshot` keyed by `next_change_id`; keep cursor logic strict so duplicate captures are avoided.
  - Because public results lag ~5 minutes, schedule polling intervals (the CLI `interval` argument) conservatively (e.g., 30-60s) and treat duplicate `next_change_id` responses as benign (already handled in the code). Private stash snapshots rely on the same cursor semantics, so the same timing constraints apply.

### Rate limits, backoff, and cursor pacing
- Every response emits `X-Rate-Limit-Policy`, `X-Rate-Limit-Rules` (comma list like `ip,account,client`), `X-Rate-Limit-<rule>` (example `10:5:10` meaning 10 hits per 5s, penalized for 10s), `X-Rate-Limit-<rule>-State`, and `Retry-After` on 429s; invalid (4xx) bursts move the app toward automatic restrictions, so parse these headers on each request and obey `Retry-After` before repeating [Doc: Developer Docs].
  - `market_harvester` already pauses `public-stash-tabs` when `_pause_after_rate_limit` sees 429; keep the existing `RateLimitPolicy`/`glean_rate_limit` helpers in sync with whatever header values appear because limits can change without notice. Also continue storing `response.headers` in `_write_request_entry` so auditing can confirm which rule (client/account) fired and how long the pause lasted.
  - For `market_harvester`, keep the capture mutex and `_ensure_token` logic in place so concurrent fetch cycles do not amplify the client rule counts; the loop should deliberately wait the interval parameter and rely on `rate_limit_max_retries`/`backoff` settings in `RateLimitPolicy` (already offered via CLI flags).
  - ClickHouse writes should not accelerate polling; keep ingestion cadence tuned by the API’s backoff values rather than how fast the database can ingest, and log pause/retry events (status reporter already records `status`/`error`).

### Terms, compliance, and operational notices
- Terms of Use clause 7 explicitly forbids scraping/mirroring data outside the documented APIs, clause 6/7/9 guard automation/macros, and third-party policy requires a visible “not affiliated” notice plus unique user agents [Doc: Terms + Developer Docs]. Cache data responsibly and, if a CLI is shipped publicly, include `This product isn't affiliated with or endorsed by Grinding Gear Games in any way.` somewhere obvious.
  - `market_harvester` should never switch to untracked endpoints; keep it limited to `public-stash-tabs` plus `api/trade/data/<cursor>` metadata calls, all of which are documented. The `StatusReporter` already marks `status`/`error` codes, so add user-facing guidance on rate limit messages if the CLI exposes logs.
  - Keep the current OAuth configuration scoped to the public endpoint path; any CLI extension should still preserve documented OAuth registration and rate-limit behavior.
  - ClickHouse retains every snapshot, so retain only data allowed by the user’s granted scopes and avoid mixing snapshots from accounts that later revoke consent; respect the documented `invalid requests threshold` by validating required query parameters before sending them upstream.

### ClickHouse schema migration hygiene
- ClickHouse (per the ClickPipes schema-change doc) automatically propagates only additive DDL—from the integration notes, `ALTER TABLE ADD COLUMN` at the end represents the only schema change that can survive replication/permanent ingestion without manual bookkeeping; dropping or reordering columns yields NULLs or fails replication [Doc: ClickHouse].
  - Any schema change touching `poe_trade.raw_account_stash_snapshot` or other ingestion tables must therefore append columns, both to maintain backward compatibility for ongoing snapshots and to keep distributed/replicated nodes in sync.
  - When new metadata columns are required (e.g., to store extra rate-limit headers or service annotations), craft additive migrations and document the new column’s default so downstream consumers know how to interpret existing rows. Avoid ALTERs that rename, drop, or move columns unless a full table rebuild and pipeline pause is part of the plan.

## Open questions / unknowns
- Do official docs promise the 5-minute delay for every realm, or is it best-effort? (Public reference only says “currently”; treat the delay as a guideline and keep the polling loop prepared for faster or slower drift especially across cheat-coded shards.)
- The exact numerical rate limits for `service:psapi` are not published; monitoring headers per response is the only reliable signal, but does the CLI need to surface thresholds to operators (e.g., log “client limit is 10/5s”)?
- Is there an explicit upgrade path if GGG decides to split the `public-stash-tabs` stream into sub-endpoints (e.g., per realm or league)? The code already loops over `realms`/`leagues`, but any future partitioning would require revalidating the checkpoint format.

## Immediate implications for task-list execution
1. Keep the CLI’s OAuth tokens, scopes, and user-agent strings in lock step with the developer docs; refresh `OAuthToken` before expiry and never embed secrets in the repo.
2. Treat each 429/`Retry-After` as authoritative; extend `market_harvester` backoff logic (already present) and persist header metadata for auditing, so we can answer “which limit fired?”.
3. Maintain additive ClickHouse migrations only; when a new `INSERT` payload requires extra rate-limit metadata, introduce a new column instead of altering existing ones, document it in migration notes, and preserve backwards compatibility for rows already in `poe_trade.raw_account_stash_snapshot`.
