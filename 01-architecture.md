# Wraeclast Ledger — Architecture (Docker + ClickHouse)

## Services (docker-compose)
- clickhouse
- market_harvester (public market collector)
- stash_scribe (private stash snapshotter)
- etl (raw -> canonical)
- chaos_scale (currency conversion + price stats)
- flip_finder (arbitrage engine)
- forge_oracle (craft EV engine)
- session_ledger (stash diff + ROI)
- ledger_api (FastAPI gateway)
- ledger_ui (Streamlit v1 / Next.js later)
- (optional) atlas_api (BuildAtlas API)
- (optional) atlas_forge (BuildAtlas autonomous generator)
- (optional) atlas_bench (PoB headless worker pool)
- (optional) atlas_coach (character progression planner)
- (optional) llm_advisor (tool-calling layer; read-only)

## Data flow
1) Ingest (bronze)
- Append-only raw payloads with timestamps and checkpoints.

2) Transform (silver)
- Canonical, typed item and listing records.
- Currency conversion series (chaos rates per time bucket).

3) Aggregate (gold)
- Price stats per item fingerprint + time bucket.
- Stash pricing suggestions.
- Flip and craft opportunities.
- Farming sessions and profit/hour.

## ClickHouse table tiers (practical schema)
Bronze (raw)
- raw_public_stash_pages(ingested_at, realm, league_hint, next_change_id, payload_json)
- raw_currency_exchange_hour(hour_ts, realm, payload_json)
- raw_account_stash_snapshot(snapshot_id, captured_at, realm, league, tab_id, payload_json)

Silver (canonical)
- item_canonical
  - item_uid, source(public/account), captured_at, league
  - base_type, rarity, ilvl, corrupted, quality, sockets/links, influences[]
  - mod ids/tier info where available
  - fp_exact, fp_loose (fingerprints for matching)
- listing_canonical
  - listing_uid, item_uid, listed_at, league
  - price_amount, price_currency, price_chaos (normalized), seller/meta
- currency_rates
  - time_bucket, league, currency, chaos_rate

Gold (analytics)
- price_stats_1h
  - league, fp_loose, time_bucket
  - p10/p25/p50/p75/p90, listing_count, spread, volatility, liquidity_score
- stash_price_suggestions
  - snapshot_id, item_uid, est_price_chaos, list_price_chaos, confidence, reason_codes[]
- flip_opportunities
  - detected_at, league, query_key, buy_max, sell_min, expected_profit, liquidity_score, expiry_ts
- craft_opportunities
  - detected_at, league, item_uid, plan_id, craft_cost, est_after_price, ev, risk_score
- farming_sessions
  - session_id, start_snapshot, end_snapshot, tag, duration_s, profit_chaos, profit_per_hour

## Partitioning and engines (recommended defaults)
- Use MergeTree-family tables partitioned by (league, toYYYYMMDD(ts)).
- Use ReplacingMergeTree for dedupe in canonical tables where re-fetch may happen.
- TTL raw tables (e.g., 14–30 days), keep gold tables longer.

## Pricing fundamentals
- Normalize all prices to chaos using time-bucketed currency rates.
- Use robust statistics (median + percentiles) rather than mean.
- Outlier/price-fixer filters:
  - percentile trimming
  - minimum listing_count
  - (optional) seller diversity heuristics

## Security and guardrails
- Collectors obey dynamic rate limits and Retry-After headers.
- LLM is read-only: only calls Ledger API tools and never writes to ClickHouse.
- Account ingestion secrets via env + Docker secrets; never log tokens.

## Minimal UI pages
- Market overview (currency + movers)
- Stash pricer (>=10c, export price notes)
- Flip scanner
- Craft advisor
- Farming ROI (session leaderboard)
- BuildAtlas (optional module: Forge/Coach + sortable build table)
