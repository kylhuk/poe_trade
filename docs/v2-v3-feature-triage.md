# v2 vs v3 feature triage

## 1 Inputs & scope constraints
- **Research backlog:** `poe1_league_currency_research_v3.md` enumerates liquidity-first strategies (market-making, asynchronous venues, low-effort craft loops, time arbitrage) and the data each idea needs.
- **Current capability gaps:** `docs/v2-gap-matrix.md` paints the live stack as deterministic/stubbed, with Ops/ingest pipelines still planning-only and ClickHouse reads additive-only by policy, so any change must be chronicled as additive (no schema deletions).
- **Repo health log:** The gap matrix also flags missing OAuth scopes/services, so our triage must honor the documented runway (deterministic service layer today, additive-only ClickHouse changes, service:psapi only at boot).
- **Data-source feasibility:** `docs/research/poe-data-sources.md` and `artifacts/planning/v2-scope-availability.txt` both confirm only `service:psapi` is granted; every `service:leagues`, `service:cxapi`, or `account:*` request is rejected (`invalid_scope`), so any feature needing those scopes is a v3 candidate per the user rule.

## 2 Matrix dimensions + grouping buckets
- **Market intelligence (public supply/price telemetry):** ideas built purely on the live public stash stream plus ClickHouse aggregates (bronze/gold tables) under service:psapi.
- **Execution/simulation (strategy backtests, sell models, automations):** features that wrap the above data into decision-ready metrics and intervention alerts; must remain additive to existing ClickHouse schema.
- **Operations & reliability (dashboard, rate limits):** tightened telemetry, drift detection, and Ops tooling referenced in the gap analysis—these are prerequisites for trusting profit decisions.
- **External scope-gated expansions:** anything requesting League metadata, Currency Exchange hourly history, or account-level snapshots is grouped for v3 deferral because the OAuth ledger lacks those scopes today.

## 3 V2 selection criteria
1. Leverage existing bronze streams (`service:psapi`) and ClickHouse tables; avoid introducing new OAuth scopes until an upgraded client appears.
2. Keep ClickHouse changes additive only (new views, distilled metrics, or derived tables) in line with the repository’s migration safety guidance.
3. Prioritize ideas that close the documented gaps (`docs/v2-gap-matrix.md`)—live Ops telemetry, alerting, and deterministic-to-real service wiring—since these unlock trustworthy profit signals.
4. Favor strategies whose payoff is measurable through the public stash feed (volume, delist timing, async listings, etc.) so we stay within the allowed scope envelope.

## 4 V3 deferral criteria
1. Requires `service:cxapi`, `service:leagues`, or `account:*` OAuth scopes; user mandate defers these features until the client is blessed or a parallel credential with those scopes is available (`artifacts/planning/v2-scope-availability.txt`).
2. Demands non-additive ClickHouse schema surgery (column/table drops, rewrites) or rewired migrations that conflict with the “additive-only” policy referenced in the gap docs.
3. Depends on major ingestion plumbing still marked as “planned” or “deterministic stub” in the gap matrix (`docs/v2-gap-matrix.md`).

## 5 Triage matrix
| Capability / Idea | Why it matters for player profit | Required data sources | Required OAuth scope(s) | Decision | Rationale | Dependencies / risks |
|---|---|---|---|---|---|---|
| Public-stash liquidity heatmaps (stackable supply + delist cadence) | Measures how fast commodity items rotate so players can liquidate at the right markup | `service:psapi` public-stash stream, ClickHouse bronze/gloss tables for historical cadence | `service:psapi` | v2 | Fits available data; addresses the “Bronze ingestion coverage” gap and informs time-to-sell models without new scopes | Depends on additive ClickHouse views/metrics; risk of stale rows until ingestion fully checkpointed (`docs/v2-gap-matrix.md`) |
| Async listing effectiveness (gold tax + cooldown impact) | Quantifies “set-and-forget” margins vs manual trading; higher sell-through reduces attention minutes and raises divines/hour | `service:psapi` listing metadata, ClickHouse timestamp columns for public listings | `service:psapi` | v2 | Directly follows research recommendation to encode venue-specific execution simulation (`poe1_league_currency_research_v3.md`) | Requires modeling buyer gold tax (estimate via listing price deltas); still additive to existing telemetry |
| Ops dashboard drift + rate-limit alarms | Ensures live telemetry/health is trusted so operators can react before profit windows close | ClickHouse `poe_ingest_status`, `raw_public_stash_pages`, telemetry tables; existing deterministic service fields replaced with real queries per remediation notes | none (internal) | v2 | Close documented blocker (`docs/v2-gap-matrix.md`); ships via additive queries | Must keep ClickHouse additions additive-only; needs admin inventory read paths only, no schema drops |
| Currency Exchange market-making simulator/backtests | Material for low-effort spreads and triangular loops; currency-exchange volume signals are core to detecting profitable pairs | Official /currency-exchange hourly history, `market_id` ratios, fill model metadata | `service:cxapi` | v3 | Requires CXAPI scope (`poe1_league_currency_research_v3.md`); user rule defers such scopes | Wait for scope blessing; once available, add new ingestion service/table (additive only) |
| Time-phase priors (day 0 launch vs mature week) | Buying what historically rallies after week 1 gives time arbitrage edges noted in `poe1_league_currency_research_v3.md` | League metadata (start/end dates), historical price curves (poe.ninja dumps or internal), event calendars | `service:leagues` (+external dumps) | v3 | Leagues scope unavailable; cannot bucket data into phases without metadata | Postpone until leagues scope unlocked; also needs stable historical dumps and phase definition tables (additive) |
| Own stash snapshot deltas / deterministic craft loop evaluation | Tracking inventory acquisitions/liquidations is essential to compute divines per attention-minute and validate deterministic craft loops | Account stash snapshot API, manually recorded craft outcomes | `account:stashes`, possibly `account:profile` | v3 | Account scopes blocked (`artifacts/planning/v2-scope-availability.txt`); repo also lacks live ingestion implementation as noted in the gap matrix (`docs/v2-gap-matrix.md`) | Once scopes arrive, implement new ingestion service and additive tables; until then rely on public listing proxies |


## 6 Most useful v2 ideas (prioritized shortlist)
1. **Ops drift + rate-limit alarms** – switch `/v1/ops/dashboard` from deterministic numbers to ClickHouse-backed signals, closing the biggest “misleading health” finding and answering the gap matrix checklist.
2. **Public-stash liquidity heatmaps** – low-friction way to compute pricing confidence and time-to-sell for commodities using only `service:psapi`, aligning with the DB-first focus in the research backlog.
3. **Async listing effectiveness alerts** – quantifies gold-tax friction and cooldowns so players can automate async stacks with confidence, and it stays within available scopes.
4. **Additive table/views for inventory layers** – label bronze/silver/gold freshness (per existing telemetry initiative) so the UI’s hero bands actually reflect live data, continuing the deterministic-to-live transition documented in the gap matrix.

## 7 V3 deferrals
### Scope-gated deferrals
- **Currency Exchange market-making simulator** – needs `service:cxapi`; blocked until the OAuth client is authorized for CXAPI. Keeps list of `market_id`s for spreads and triangular arbitrage loops once available (`poe1_league_currency_research_v3.md`).
- **League-phase priors and regime models** – requires `service:leagues` to know league start/end dates before tagging data; also depends on league timeline research (`poe1_league_currency_research_v3.md`).
- **Account-stash-based strategy telemetry** – needs `account:stashes` (and optionally `account:profile` to confirm builds) which are currently `invalid_scope` responses (`artifacts/planning/v2-scope-availability.txt`).

### Non-scope deferrals
- **Non-additive ClickHouse rewrites (deterministic → live)** – some API endpoints still rely on seeded fixtures; while replacing them is high impact, the change demands additive-only schema changes plus new ingestion writers, so it stays in v3 until the stack stabilizes.
- **Multi-venue service economy modeling (TFT + PoEDB enrichment)** – enriching mod/craft metadata is valuable (`poe1_league_currency_research_v3.md`, `docs/research/poe-data-sources.md`), but ingestion points are brittle and best deferred until the core bronze/gold rollers and ClickHouse additive pipelines are proven.
