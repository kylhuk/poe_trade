# Wraeclast Ledger — Ecosystem Overview

Date: 2026-02-21

## What this ecosystem does
A Dockerized analytics stack (ClickHouse as the only database) for Path of Exile trading and build decisions:

- Ingests market data and your account stash snapshots.
- Normalizes prices into chaos (time-aware conversion).
- Produces actionable outputs:
  - “Price my stash” (only items with estimated value ≥ 10 chaos).
  - Flip/arbitrage candidates.
  - “Small craft → big value” candidates with expected value (EV).
  - Farming ROI via stash diffs and sessions.
- Adds two power tools:
  - **ExileLens** (Linux capture): reads item text via clipboard and/or OCR and calls the backend for instant analysis.
  - **BuildAtlas**: autonomous build discovery + build coach (PoB-powered). Generates diverse builds and ranks them by power/cost/difficulty; includes “Surprise Build”, upgrade roadmaps, and patch radar.

## Named tools (components)
- **MarketHarvester**: Public market ingestion (public stash stream, currency exchange history).
- **StashScribe**: Account stash snapshotter + stash pricing suggestions (>=10c) + exports.
- **ChaosScale**: Currency normalization and price statistics builder (p10/p50/p90, liquidity, volatility).
- **FlipFinder**: Flipping/arbitrage opportunity engine (underpriced listings, spreads, bulk premiums).
- **ForgeOracle**: Craft EV engine (deterministic first; later probabilistic) + craft plan explanations.
- **SessionLedger**: Farming ROI tracker via stash diffs (profit/hour by tagged strategy).
- **Ledger API**: FastAPI backend exposing read-only tools for UI and LLM (prices, comps, flips, crafts, sessions).
- **Ledger UI**: Dashboard (Streamlit v1 or Next.js later).
- **ExileLens**: Linux client: clipboard-first + optional screenshot/OCR capture to analyze hovered items.
- **BuildAtlas**: PoB-powered autonomous build discovery (AtlasForge) + progression guide (AtlasCoach), with sortable tables by cost/power/difficulty and patch radar.

## Integration principles
1) **ClickHouse is the source of truth**
- All collectors write to “bronze” raw tables.
- ETL produces canonical “silver” tables.
- Analytics writes “gold” tables.
- UI and LLM read only from silver/gold via the API.

2) **One internal API surface**
- Everything that needs “analysis” calls **Ledger API**:
  - ExileLens (item analysis)
  - UI (dashboards)
  - LLM advisor (read-only tool calling)

3) **Deterministic numbers, LLM for narration**
- Prices, EV, and rankings come from deterministic code + statistics.
- LLM outputs are explanations and action plans using numbers fetched from the API (no invented prices).

## Suggested repository layout
- `/services/market_harvester`
- `/services/stash_scribe`
- `/services/etl`
- `/services/chaos_scale`
- `/services/flip_finder`
- `/services/forge_oracle`
- `/services/session_ledger`
- `/services/ledger_api`
- `/services/ledger_ui`
- `/clients/exile_lens` (Linux desktop tool)
- `/services/build_atlas` (PoB evaluator + build ranking)

## API contracts (core)
- `POST /v1/item/analyze` — parse + price + craft suggestions for a single item (clipboard/OCR).
- `POST /v1/stash/price` — generate stash price suggestions for a snapshot.
- `GET /v1/flips/top` — current flip candidates.
- `GET /v1/crafts/top` — current craft candidates.
- `POST /v1/sessions/start` / `POST /v1/sessions/end` — create farming sessions (snapshots + diff).
- `GET /v1/builds/search` — BuildAtlas search/filter/sort.
- `GET /v1/builds/{build_id}` — BuildAtlas detail (scenario stats + cost + difficulty).

## Operational defaults
- Prefer **clipboard-first** extraction for items (most reliable).
- Use OCR as a fallback or on X11 where capture is smooth.
- Partition all time series by league + day in ClickHouse.
- Apply TTL on raw tables; keep aggregates longer.
