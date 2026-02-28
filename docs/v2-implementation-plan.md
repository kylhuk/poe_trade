# v2.0 Implementation Plan | Low-Effort Profit Engine

## 1 Executive objective for player profitability
- **Target metric stack:** 0.5+ divines per attention-minute (primary), 5+ divines/day under an attention cap, 90% sell-through within 6 hours for commodity stacks, drawdown capped at 15% of average weekly profit, and time-to-sell median for tracked commodities under 3 hours. These targets adopt the “divines per attention-minute” framing from the low-effort strategy research and embed sell-through and drawdown metrics so every automatable signal directly answers the profitability ambition (`poe1_league_currency_research_v3.md`:14-26, 270-280). 
 - **Attention economy boundary:** limit alerts/automation to scenarios where the net attention-minute delta is positive (i.e., alerts should not push the player to chase <0.3 divines/minute opportunities). Time-to-sell modeling and liquidity priors ensure the UI does not promote stale listings, closing the “Bronze ingestion coverage” blocker in the gap matrix (`docs/v2-gap-matrix.md`:16-22).

## 2 Current-state blockers and what v2 solves
| Blocker | Consequence | v2 Solution | Source |
|---|---|---|---|
| Staged ingestion + deterministic APIs | Players can’t trust pricing or alerts; overlays act on stale cash-in data | Fully checkpointed bronze→silver→gold ingestion and ClickHouse-backed telemetry upgrade the Ops dashboard and alerts (`docs/v2-gap-matrix.md`:6-20). | `docs/v2-gap-matrix.md` |
| Alert surfaces are planning-only and lack prioritization | Operators refresh UI manually, missing high-velocity flips | Wire UI alerts to live ClickHouse views and add overlay with filters/hotkeys to protect against misclicks (`docs/ops-runtime-ui-upgrade-plan.md`, `07-exilelens-overlay-plan.md`, `10-comprehensive-feature-backlog.md`) |
| Rate-limit/drift guard gaps | Scripts risk PoE bans; confidence drops when ingestion stalls | Implement ops runbook guardrails (checkpoint drift, throttler, fallback) so automated flips stay within service:psapi usage (`docs/ops-runbook.md`:8-21; `06-db-etl-roadmap.md`:24-231) |

 The v2 build directly addresses these blockers by delivering live ingestion surfaces, real alerts, and reliability tooling while staying additive-only due to the ClickHouse constraint (`docs/v2-gap-matrix.md`:16-22, `docs/v2-v3-feature-triage.md`:1-5).

## 3 Scope boundary (v2 vs v3)
### v2 scope means
- Only `service:psapi` feeds; no `service:cxapi`, `service:leagues`, or `account:*` scopes (`artifacts/planning/v2-scope-availability.txt`:3-15).
- ClickHouse schema changes must be additive (views, derived tables, telemetry metrics) per the repo rules (`docs/v2-gap-matrix.md`:16-22).
- UX upgrades target Streamlit/NiceGUI surfaces and overlay helpers; no major league metadata or account-level ingestion.

### v3 parking gated by OAuth or schema risk
| Feature class | Gate | Action |
|---|---|---|
| Currency Exchange simulator (market-making, triangular arbitrage) | `service:cxapi` only available v3 (`poe1_league_currency_research_v3.md`:116-142; `artifacts/planning/v2-scope-availability.txt`:7-12) | Defer to v3 once CXAPI granted, keep additive table blueprint ready (
v3 parking lot has dedicated section). |
| League-phase models | `service:leagues` | Hold until scope unlock; reuse ingest templates for regimes once metadata available (`poe1_league_currency_research_v3.md`:120-138). |
| Account stash/craft snapshots | `account:*` | Fully v3; meanwhile rely on public stream proxies for liquidity (`poe1_league_currency_research_v3.md`:88-121; `artifacts/planning/v2-scope-availability.txt`). |

## 4 Target architecture (planes)
1. **Data plane:** Bronze entries from `service:psapi` public stash stream plus trade metadata feeds (`/api/trade/data/*`) and poe.ninja valuation snapshots (`docs/research/poe-data-sources.md`:30-105). Data funnels through checkpointed bronze tables, stores `sample_time_utc` from poe.ninja, and tracks stream cursors in ClickHouse exposures (additive, real-time views). PoEDB enrichment is optional & compliance-safe; harvest only when JSON endpoints are stable, with a staged ingestion workflow and retention of raw payload for auditing (`docs/research/poe-data-sources.md`:63-78). Ouput: raw ledger tables plus quick-look materialized views.
2. **Compute plane:** Silver normalization pipelines build canonical item keys (base type, rarity, league, mods) fed by gold views that compute liquidity metrics (time-to-sell, sell-through, drawdown) using poe.ninja and public-stash delist cadence heuristics. Confidence scoring attaches probability-of-sale and divines per attention-minute metrics, referencing the “Strategy evaluation metrics” section (`poe1_league_currency_research_v3.md`:657-675). Derived ClickHouse views remain additive and can be exposed to the UI and strategy engine.
3. **Experience plane:** NiceGUI dashboard plus overlay controls surface live alerts, liquidity heatmaps, time-to-sell signals, and the Streamlit-to-NiceGUI migration path. UX also powers overlay, audible/visual notifications, and actionable buttons for quick sell/edit actions.

## 5 Bronze ingestion design
- **Sources:** official psapi public stash stream (primary), trade metadata endpoints (`/api/trade/data/*`) for normalization, poe.ninja feeds/dumps for price snapshots (`docs/research/poe-data-sources.md`:30-121), and a compliance-safe PoEDB pathway (only ingest when endpoints respond and log all requests; if the CLI detection sees `404` or certificate hiccups, mark enrichment as deferred and retry daily). Do not scrape unsupported surfaces; PET data is only enrichment. All ingestion obeys `service:psapi` scope; no `cxapi` legs.
- **Continuous mechanisms:** Bronze workers maintain per-queue cursors stored as `last_cursor_id` with timestamp; workers checkpoint after every successful page to guarantee idempotency. Each job logs `retrieved_at`, `cursor_hash`, and `retry_count`. Poe.ninja feeds use incremental `sample_time_utc` plus local cache TTL (3 minutes) to avoid over-requesting. Trade metadata is cached per league/realm and refreshed only when `updated_at` (X-Rate-Limit) changes.
- **Cadence:** Public stash poll every 10 seconds per `service:psapi` recommended pacing; metadata endpoints once per patch, poe.ninja once per league per minute (throttle to ~1 rps to avoid Cloudflare bans). poedb enrichment staged daily, skip on `404`/`429` and escalate only after 3 consecutive successes.
- **Checkpointing & retries:** Bronze ingestion writes to `bronze_public_stash`, `bronze_trade_metadata`, `bronze_poeninja_snapshot` tables plus `bronze_ingest_checkpoints`. Retries follow exponential backoff up to 3 attempts, logging `retry_reason`. Worker ensures idempotency by deduping on `listing_id` + `cursor`. All writes go through insert-only ClickHouse mutations (e.g., `INSERT INTO ... SELECT ...`), honoring additive-only rule.
- **Schema topics:** Primary fields include `league`, `listing_id`, `seller`, `price_currency`, `price_amount`, `stack_size`, `timestamp`, `item_type_id`, plus `ids_from_trade_metadata` (e.g., `item_type`, `variation_id`). Poe.ninja ingestion stores `detailsId`, `chaosEquivalent`, `listing_count`, `sparkline`, and `sample_time_utc`. PoEDB enrichment appends `mod_id`, `mod_description`, `craft_group`. All schema updates use additive JSON columns or new tables to keep compatibility.

## 6 Silver/Gold design
- **Silver normalization priorities:** (1) map trade metadata IDs (`trade_category`, `item_type`, `variation`) into canonical base + tag; (2) add normalized price per chaos/divine + gold-tax-adjusted price; (3) enrich with poe.ninja price tiers and mod metadata when available; (4) flag liquidity buckets (commodity, gear, services) for selecting heuristics. These priorities resolve the canonical item and price coverage gaps from the matrix (`docs/v2-gap-matrix.md`:18).
- **Gold profitability products/signals:**
  - Liquidity heatmap view (stackable supply + time-to-sell) feeding divisor per attention-minute scoring, derived from public stash cadence and `poe1_league_currency_research_v3.md` signals.
  - Async listing effectiveness alert that computes gold-tax drag vs manual market price, bending `poe1_league_currency_research_v3.md`:243-266 into an automation cue.
  - Confidence scoring per signal capturing probability of sale within 6 hours, expected drawdown, and sparkline volatility. Each score includes freshness metadata (sample timestamp) and a “stale if older than 10 minutes” flag. Confidence also tracks `divines_per_attention_minute_estimate` using logistic regression or rule-based heuristics referencing the research metrics (`poe1_league_currency_research_v3.md`:22-27, 623-675).
- **Freshness handling:** When a signal’s underlying data (public stash, poe.ninja, overlay ack) exceeds its TTL (10 minutes for listing data, 5 minutes for poe.ninja), the UI shifts to “requerying” and the scoring tier drops to amber. Derived tables capture `last_ingest_ts` so the strategy engine can detect drift and trigger ops guardrails.

## 7 Strategy engine v2 features
- **Low-effort venue modeling:** Use `service:psapi` to track public-stash frequency and delist timing per commodity, create heatmaps for stackable supply, and align those with async listing dominance per research (`poe1_league_currency_research_v3.md`:98-136). Each venue (currency exchange, async, manual) attaches a friction profile (gold tax, cooldown) derived from the research doc and ensures modeling respects the available scopes.
- **Time-to-sell/liquidity components:** Build a `v_liquidity(item_id, league)` view showing median sell-through, delist rate, and expected time-to-sell; integrate this view into `v_strategy_pnl` so features like sell-through ratio, liquidity score, and drawdown band feed the attention-minute optimizer (`poe1_league_currency_research_v3.md`:148-206, 270-310, 623-676). Use dev-time sync jobs to run scenarios (commodity stack vs async listing) so attention cost is explicit and biases toward stable, low-variance opportunities.
- **Confidence/scoring:** Each strategy run stores `gross_profit`, `net_profit`, `divines_per_attention_minute`, `turnover`, and `max_drawdown` per `7.4 Strategy evaluation metrics` to keep the engine grounded in measurable performance (`poe1_league_currency_research_v3.md`:657-675).

## 8 Notifications & UX
- **Web UI alert center:** NiceGUI (targeting an incremental Streamlit → NiceGUI migration) exposes an alerts table with severity, attached stats, and audible chimes for critical events (e.g., liquidity drop >40% or diverging gold tax). Alerts can be acknowledged or snoozed, and severity resets when new data arrives. Streamlit keeps a read-only view during the cutover, ensuring v2 delivers value even before NiceGUI fully replaces it (`docs/ops-runtime-ui-upgrade-plan.md`:3-99).
- **Migration path:** Start by embedding NiceGUI components inside the existing Streamlit layout (hero alert cards, severity badges) while the backend still serves both frontends. Once NiceGUI covers the alert center, retire the Streamlit sections. Data pipes remain the same (ClickHouse views + strategy signals), so front-end switch is additive.
- **Overlay utility:** Build a transparent always-on-top window (Electron or NiceGUI overlay) with filters/hotkeys for listing types (currency, gear, services). Provide anti-misclick guardrails by requiring double confirmation for sale >5 divines or showing dim masks when the attention score is low (per the overlay plan `07-exilelens-overlay-plan.md`:1-59). The overlay listens to alerts and can mute/disarm per player preference.

## 9 Ops/reliability/self-healing roadmap
- **Drift guard behavior:** Monitor `last_ingest_ts` for each bronze table; if data lags >20 seconds, trigger an alert that also wakes a self-heal job to restart the worker and log in `ops_drift_log`. Each alert includes the checkpoint reason and the `divines per attention-minute` signal that is stale.
- **Rate-limit safety:** Bronze workers parse `X-Rate-Limit-*` headers on every response, back off exponentially when `429` arrives, and fall back to cached trade metadata until the API recovers. The aperture is enforced by the governance plan in the gap matrix (`06-db-etl-roadmap.md`:24-231).
- **SLOs:** 95% of bronze data must land within 60 seconds, 99% of alerts must trigger within 30 seconds of a signal crossing a threshold, and overlay state must sync within 15 seconds. Ops-runbook sequences capture manual steps for SLO violation, referencing `docs/ops-runbook.md`:1-21.
- **Rollback/fallback:** If ingestion failure persists 3 retries, automatically disable the affected signal, mute overlay alerts for that class, and create a “manual refresh” button linking to the ops runbook. Archive the failure in ClickHouse for post-mortem and automatically resume when the worker reestablishes success.

## 10 Milestone plan (phased)
### Phase 1 – Groundwork (weeks 1-2)
 - Deliverables: bronze ingestion jobs running from psapi + poe.ninja feeds, ClickHouse checkpoint tables, initial ops monitor view.
 - Acceptance: bronze tables ingest >90% of `public-stash` cursors for 10 minutes; ops view reads checkpoint timestamps; poe.ninja ingestion writes `sample_time_utc` field.
 - Evidence: query logs showing cursor progress and a dashboard screenshot referencing `docs/v2-gap-matrix.md`:6-22.

### Phase 2 – Strategy signals + UX (weeks 3-4)
 - Deliverables: liquidity heatmaps, async listing effectiveness alerts, NiceGUI alert center stub, overlay prototype with guardrails.
 - Acceptance: derived views populate `divines per attention-minute` estimates, overlay fires audible alerts with snooze, and alert center shows severity cards with clickable drill-ins.
 - Evidence: NiceGUI alert logs, overlay usage recording, ClickHouse view definitions capturing scoring logic (`poe1_league_currency_research_v3.md`:623-675).

### Phase 3 – Reliability + Ops automation (weeks 5-6)
 - Deliverables: drift guard automation, rate-limit handling tuned, SLO dashboard, fallback workflows.
 - Acceptance: SLO dashboard shows uptime >99%; drift guard self-heals within 1 round trip; rate-limit guard halts ingestion within one throttled response.
 - Evidence: runbook updates referencing the automated recovery steps, logs of self-heal triggers, SLO chart snapshots.

## 11 V3 parking lot
- **Scope-gated:** Currency Exchange market-making + triangular arbitrage simulator, league-phase modeling, account stash snapshots/strategy telemetry (`poe1_league_currency_research_v3.md`:116-210, `artifacts/planning/v2-scope-availability.txt`:5-15). Keep these ideas documented and queue them for when the scopes unlock.
- **High-risk:** Non-additive ClickHouse rewrites (e.g., replacing deterministic APIs with new tables) and brittle PoEDB scraping. Only revisit once the additive v2 pipelines stabilize (`docs/v2-v3-feature-triage.md`:49-51).

## 12 Risks, assumptions, and decision log
- **Risk:** PoEDB endpoints may stay offline. Mitigation: schedule enrichment as staged job with graceful degrade; if unreachable 3x in a row, mark latest data as stale and rely on poe.ninja + wiki data (`docs/research/poe-data-sources.md`:63-78).
- **Assumption:** `service:psapi` remains available and continues exposing listing metadata; confirm weekly via automated scope audit and log failures as `ops_scope_audit` entries (`artifacts/planning/v2-scope-availability.txt`).
- **Decision:** Defer every CXAPI/leagues/account feature to v3 until the OAuth client is authorized, keeping documentation in this plan so the gate remains explicit (`docs/v2-v3-feature-triage.md`:22-51).
