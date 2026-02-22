# Wraeclast Ledger — Implementation Tasklist

## Epic 0 — Conventions
- Decide: realm(s), league(s), normalization currency (chaos), time buckets (15m/1h).
- Define thresholds:
  - stash sellable: est_price_chaos >= 10 AND confidence >= X
  - craft candidate: EV >= Y, risk_score <= Z
- Shared config module (env-driven) reused across services.

## Epic 1 — Docker + ClickHouse baseline
- Repo layout + docker-compose with healthchecks.
- ClickHouse migrations runner (idempotent).
- Separate CH users/roles: writer vs read-only.

DoD: `docker compose up` starts everything; schema bootstraps automatically.

## Epic 2 — ClickHouse schema (bronze/silver/gold)
- Create bronze/silver/gold tables (see architecture doc).
- Add partitions + TTL policies for raw tables.
- Add basic sanity queries and row-count dashboards.

DoD: sample inserts + queries succeed; migrations are repeatable.

## Epic 3 — Shared API client (rate-limit compliant)
- HTTP client that:
  - parses X-Rate-Limit headers
  - respects Retry-After
  - bounded retries + backoff + jitter
- Unit tests for header parsing and backoff.

DoD: client survives throttling without hammering.

## Epic 4 — MarketHarvester (public ingestion)
- Public stash stream ingestion:
  - checkpoint `next_change_id`
  - persist each page payload to bronze
- Currency exchange hourly ingestion to bronze.

DoD: continuous ingestion for multiple hours with stable resume after restart.

## Epic 5 — StashScribe (account ingestion)
- OAuth flow + refresh handling.
- Snapshot all stash tabs into bronze with snapshot_id and captured_at.
- Scheduler + manual trigger endpoint.

DoD: one command produces a complete stash snapshot in ClickHouse.

## Epic 6 — ETL v1 (raw -> canonical)
- Parse raw public pages into item_canonical + listing_canonical.
- Parse account snapshots into item_canonical (source=account).
- Build fingerprints fp_exact/fp_loose.
- Data quality checks (parseable prices %, invalid price counts).

DoD: canonical tables have stable volumes and sane values.

## Epic 7 — ChaosScale (normalization + stats)
- Build currency_rates by league/time bucket.
- Normalize listing prices into price_chaos.
- Aggregate to price_stats_1h with robust percentiles + liquidity/volatility.

DoD: for any fp_loose you can query p50 and comps_count.

## Epic 8 — Stash pricer (>= 10c)
- Pricing endpoints:
  - item estimate (with comps)
  - batch estimate for snapshot_id
- Write stash_price_suggestions for items above threshold.
- UI page + export price notes.

DoD: picking a snapshot yields a sorted list of sellable items with suggested prices.

## Epic 9 — FlipFinder (arbitrage engine)
- Underpriced listing detector vs p25/p50-MAD thresholds.
- Bulk vs single premium detector (where possible).
- Opportunity decay/expiry and dedupe.
- UI page “Flip scanner”.

DoD: small set of high-confidence flips with buy_max/sell_min and liquidity score.

## Epic 10 — ForgeOracle (craft EV, deterministic first)
- Craft action registry (v1: deterministic/low-risk upgrades).
- Feasible plan enumeration (1–3 steps).
- EV calculation: est_after - current - cost - risk_penalty.
- Persist craft_opportunities and surface in UI.

DoD: list of positive-EV craft candidates with explainable steps.

## Epic 11 — SessionLedger (farming ROI)
- Start/end session workflow:
  - snapshot at start
  - snapshot at end
  - tag + duration
- Diff computation and valuation with pricing engine.
- UI “Farming ROI” leaderboard.

DoD: profit/hour by tag is measurable and comparable.

## Epic 12 — Ledger API + UI integration
- API endpoints for all gold outputs.
- UI pages:
  - Market overview
  - Stash pricer
  - Flip scanner
  - Craft advisor
  - Farming ROI

DoD: no manual ClickHouse queries needed for daily use.

## Epic 13 — ExileCoach (LLM advisor; read-only)
- Tool endpoints (read-only) and prompt rules:
  - must use tool numbers; no invented prices
- UI panel “Daily Plan”.

DoD: advisor returns an actionable plan linked to computed outputs.

## Epic 14 — Hardening
- Backfills/replays from checkpoints.
- Monitoring: ingestion lag, error rate, CH query latency.
- Retention + compaction.
- Load tests for pricing endpoints.


## Epic BA1 — BuildAtlas Bench (PoB headless eval pool)
- Containerize a headless PoB evaluator (locked down: no network, non-root, CPU/RAM limits).
- Worker pool that:
  - accepts a build genome / PoB XML
  - evaluates standardized scenarios
  - returns typed metrics + validation flags
- Caching of repeated evaluations (same genome hash).

DoD: given a genome, you can get scenario metrics reliably and fast.

## Epic BA2 — Build genome spec + structured-random generator (AtlasForge MVP)
- Define a JSON genome that fully defines:
  - ascendancy/class, main skill, supports, auras
  - passive nodes list
  - gear spec (unique ids and/or “rare templates”)
  - scenario toggles
- Implement a “structured random” generator:
  - skill/ascendancy compatibility constraints
  - baseline viability constraints (resists, attributes, reservation)
- Persist genomes and initial evals to ClickHouse.

DoD: one click produces a table of random-but-valid builds.

## Epic BA3 — Ranking + table UI
- Compute derived metrics:
  - power_score per scenario
  - difficulty score with reason codes
  - cost distribution (p10/p50/p90) via Ledger pricing
  - meta-risk score (volatility/liquidity-based penalty)
- UI page “BuildAtlas”:
  - sortable/filterable table (cost, DPS, EHP, difficulty)
  - build detail view + PoB export

DoD: you can sort by “best build for lowest price”.

## Epic BA4 — Evolutionary search + diversity pressure (AtlasForge v2)
- Maintain a population of genomes.
- Add mutation operators (tree/gems/auras/gear template swaps).
- Select by multi-objective Pareto + novelty bonus.
- Run as a scheduled job (nightly) and on-demand (button).

DoD: build quality improves over time without collapsing to one meta solution.

## Epic BA5 — Rare item templates catalog (enables realistic gear synthesis)
- Mine market data to cluster rares per slot into “templates”:
  - stats vector + price distribution + liquidity
- Gear synthesis:
  - choose templates to satisfy resists/attributes
  - optimize for objective under budget

DoD: builds have realistic, priceable rare gear without exploding search.

## Epic BA6 — AtlasCoach (character progression planner)
- Import character state (PoE API or PoB export).
- Evaluate current state with PoB scenarios.
- Propose upgrade steps:
  - passive point path (marginal gain per point)
  - gem upgrades/links
  - gear upgrades ranked by “gain per chaos”
- UI: “Coach” page with shopping list and step-by-step plan.

DoD: given your current character, it produces a credible roadmap and costed upgrade list.

## Epic BA7 — Patch Radar
- Detect PoB/game-data version changes.
- Mark builds stale and re-evaluate priority sets.
- Run targeted searches around changed skills/gems.
- Output “delta leaderboard” (biggest gains vs previous version), filtered by cost/meta-risk.

DoD: you can quickly see newly strong, still-cheap builds after changes.
