# PoE1 League Currency Research (Trade Leagues, Data-Driven, Low Effort)

Scope: Path of Exile 1 **challenge leagues only** (fresh economies), prioritising **maximum currency per unit attention** via trading, market-making, low-friction crafting, and bulk liquidation.  
Non-goals: Standard, RMT, botting, and any automation that violates GGG’s third‑party policy or in-game macro rules.

This document is written to be “DB-first”: every strategy is framed as something you can **detect, simulate, and backtest** against your own stash snapshots + market data.

---

## 0) Define “low effort” in measurable terms

“Low effort” should be treated as a constraint you can measure and optimise, not a vibe.

Practical proxies you can store per strategy run:

- **Attention minutes/day** (how long you actively trade/craft).
- **Interactions/day** (whispers, hideout visits, clicks).
- **Inventory friction** (unique item count moved vs stackables moved).
- **Variance** (profit volatility; drawdown vs time).
- **Liquidity** (time-to-sell distribution; percent of inventory sold within N hours).

Optimisation target suggestion:

- Primary: **divines per attention-minute**.
- Secondary: **divines/day** subject to a cap on attention-minutes.

---

## 1) Trading venues in modern PoE1 leagues (and how they change strategy)

Since 3.25+ (Currency Exchange) and 3.27+ (Asynchronous Trade + in-game market UI), “trading” is not one market. It is multiple venues with different frictions. Model each venue explicitly.

### 1.1 Currency Exchange Market (stackables)

What it is: an in-game order system for **stackable commodities** (currencies, fragments, div cards, fossils/resonators, omens, and other Currency Tab extras).  
Unlock: through **Faustus in Act 6**, trade-enabled leagues only.  
Constraints: gold fee per order; max 10 active orders; partial fills; historical API is hourly and not current-hour.

Why it matters for low effort:
- It is the closest thing PoE has to “set orders and let them fill”.
- It supports **market-making** and **passive rebalancing**.

Primary sources:
- Currency exchange mechanics + what can be traded: https://www.poewiki.net/wiki/Currency_exchange_market
- Official API (hourly aggregated history): https://www.pathofexile.com/developer/docs/reference (Currency Exchange section)

### 1.2 Asynchronous item trading (Merchant Tabs)

What it is: asynchronous buyout of **non-currency items** using **Merchant Tabs** managed by Faustus. Buyers travel to your hideout and buy directly, even if you’re offline.

Key economics (important for modelling):
- **Buyer pays a gold “tax” fee** in addition to the listed currency price.
- **No fee to list**, but there are **cooldowns/constraints** on removing or repricing after an item becomes listed.
- Earnings arrive into dedicated **Earnings tabs**; if they fill up, you can be blocked from listing until claimed.

Low-effort implication:
- You can list a lot of items in batches and let sales happen offline.
- Because the buyer pays gold, very cheap items may sell worse (gold cost becomes a large % of the total cost).

Primary sources:
- Mechanics, unlock, gold tax, cooldown notes: https://www.poewiki.net/wiki/Asynchronous_trading
- Example explainer (secondary): https://mobalytics.gg/poe/guides/merchant-tabs-and-async-trading-with-faustus

### 1.3 Manual trade (trade site + whispers)

Still exists. Still important for:
- **Bulk deals** that would be gold-inefficient on Currency Exchange.
- Items where the async gold tax suppresses demand.
- Niche markets where you need negotiation, services, or “bundle” deals.

Low-effort stance:
- Treat manual whisper trading as “high attention”.
- Use it mainly as a liquidation tool (sell once/day) or for occasional high-margin arbitrage.

### 1.4 In-game Trade Market UI (3.27+)

PoE1 now has an in-game trade market UI that works like the trade website (search/buy flow). This reduces friction for buyers, which generally increases sale probability for fairly priced listings.

Primary source:
- Asynchronous trading version history mentions in-game trade market UI: https://www.poewiki.net/wiki/Asynchronous_trading

---

## 2) Data you should ingest (minimum viable, legally obtainable)

### 2.1 Your account stash snapshots (ground truth inventory)

- OAuth scope: `account:stashes`  
- Endpoints: `/stash/<league>`, `/stash/<league>/<stash_id>` etc.  
- Source: https://www.pathofexile.com/developer/docs/reference (Account Stashes)

Recommended approach:
- Snapshot all tabs at fixed intervals (e.g., every 10–30 minutes while online).
- Store item JSON + a stable item hash for dedupe.
- Derive “you acquired X between snapshots” (loot deltas).

### 2.2 Public stash tabs stream (supply + listing behaviour)

- OAuth scope: `service:psapi`  
- Endpoint: `/public-stash-tabs`  
- Notes: the API has a **delay** (currently documented as 5 minutes).  
- Source: https://www.pathofexile.com/developer/docs/reference (Public Stashes section)

Use cases:
- Supply shocks (new farming meta floods the market).
- Detecting liquidity (how often an item appears/disappears).
- Estimating “sell-through” for commodity-like items.

### 2.3 Currency Exchange hourly history (the best low-effort alpha feed)

- OAuth scope: `service:cxapi`  
- Endpoint: `/currency-exchange/<id>` (hourly digests; no current hour)  
- Returns: `market_id` plus dictionaries for volume and ratios.  
- Source: https://www.pathofexile.com/developer/docs/reference (Currency Exchange section)

Why it’s powerful:
- It includes **volume_traded**, which is essential for filtering out dead pairs.
- You can model spreads and volatility without scraping.

### 2.4 League metadata (for phase models)

- OAuth scope: `service:leagues`  
- Endpoint: `/league` includes `startAt` and `endAt`.  
- Source: https://www.pathofexile.com/developer/docs/reference (Leagues section)

Use:
- Automatically bucket data into “day 0–2”, “week 1”, etc.
- Detect partial leagues / events.

### 2.5 External price history (for cross-league phase modelling)

- poe.ninja PoE1 data exports: https://poe.ninja/poe1/data  
- PoE Antiquary: https://poe-antiquary.xyz/

Use cases:
- “What always rises after day 3?”
- “What crashes by week 3?”
- Build league-phase priors before you have enough in-league data.

---

## 3) League economy phases and what changes (model as regimes)

Your models should be regime-aware; the same action has different ROI depending on timing.

### Phase A: Launch → Day 2 (scarcity, chaos)

Market properties:
- Scarcity of everything.
- Huge convenience premium for progression-enabling items.
- Extreme volatility; price history is weak; liquidity is thin.

Low-effort edges:
- Sell progression commodities instead of hoarding.
- Flip “boring” but necessary things (maps, basic crafting currency) if spreads are massive.
- Avoid niche long-holds unless historically reliable.

DB tests:
- Measure how fast early-game commodities sell at different markups.
- Track chaos/divine ratio curve (if you treat divine as store-of-value).

### Phase B: Day 3 → Day 10 (market formation)

Properties:
- Mapping ramps up.
- Currency Exchange volume increases dramatically.
- Farming metas start to stabilise.

Low-effort edges:
- Turn on Currency Exchange market-making for high-volume pairs.
- Specialise into 1–2 commodity mechanics (Harvest, Essence, Expedition, etc.).
- Begin simple deterministic crafts with high sell-through (see Section 6).

DB tests:
- Identify pairs with stable spread + high volume.
- Train a baseline time-to-sell model for common commodities.

### Phase C: Weeks 2–6 (mature market)

Properties:
- Competition increases; spreads tighten.
- “Best” farming strategies become common knowledge.
- Prices reflect meta builds.

Low-effort edges:
- Focus on liquidity and repeatability: bulk conversion + async listing.
- Raise thresholds: only take trades with strong margins after realistic slippage.

DB tests:
- Strategy ranking by divines per attention-minute.
- Identify items where async trading increases sell-through vs manual.

### Phase D: End-of-league (liquidity collapse)

Properties:
- Fewer buyers; demand for progression drops.
- Many niche items become illiquid.
- “Store of value” behaviour dominates (divines, mirrors).

Low-effort edges:
- Liquidate niche inventory early.
- Keep only high-liquidity stores of value and the fastest-selling commodities.

DB tests:
- Time-to-sell explodes; update liquidation thresholds.

---

## 4) Strategy taxonomy (everything you can test on data)

### 4.1 Liquidity premium and bulk convenience

Core idea: sell the same goods at a premium by being the easiest seller.

Testable hypotheses:
- Bulk stacks sell faster even at worse unit price.
- “One price, no negotiation” increases sell-through.

DB signals:
- Stack size vs time-to-sell curve.
- Premium you can charge for “instant bulk”.

### 4.2 Currency Exchange market-making (most scalable low-attention strategy)

Core idea: be the spread. Place maker orders; let fills happen.

Critical modelling details:
- Gold cost exists; treat it as a “fee budget”.
- Fills are not guaranteed; you need an empirical fill model.

Backtests:
- For each `market_id`:
  - Volume filters (minimum `volume_traded`).
  - Spread estimate from `lowest_ratio`/`highest_ratio`.
  - Volatility estimate (range width and regime shifts).

Execution rules (to simulate):
- Inventory caps per currency.
- Stop-loss / unwind rule when ratios move against you.
- “Do not chase” rule to avoid overtrading.

### 4.3 Triangular and multi-leg arbitrage (Currency Exchange)

If A/B, B/C, and A/C markets exist, you can test triangular loops:

- Compute implied cross-rate from two markets.
- Compare to direct market.
- Only act if net profit exceeds:
  - gold costs,
  - expected slippage,
  - your attention cap.

This is especially relevant if some markets are much more liquid than others.

### 4.4 Cross-venue arbitrage (Exchange ↔ manual ↔ async)

Why divergence exists:
- Currency Exchange has gold fees and different participants.
- Async item purchases add buyer gold tax.
- Manual trading has attention friction and negotiation.

Backtests:
- Build “synthetic mid price” from public listings (or external price sources).
- Compare to Currency Exchange ratios.
- Trigger only on large divergence with strong liquidity.

Compliance note:
- Keep this as analysis + alerts; avoid bot-like whisper automation.

### 4.5 Time arbitrage (league-phase investing)

Core idea: buy what predictably rises later.

Make it data-driven:
- For each item/currency, compute a “typical curve” across past leagues:
  - median price by day,
  - day-of-peak distribution,
  - drawdown probability.

In PoE, typical targets include:
- Store-of-value currencies (league-dependent).
- High-end crafting inputs that become relevant after most players reach endgame.
- Meta uniques/jewels/gems once build guides spread.

### 4.6 Deterministic craft loops (repeatable value-add)

This is where “little effort” can beat pure farming if you:
- batch process,
- avoid judgement-heavy rare evaluation,
- sell only highly liquid outputs.

Examples of loops to model:
- Essence spam on rings/belts/boots with strict acceptance rules.
- Harvest lifeforce conversion into specific crafts (or into commodities).
- Fossil crafting on a narrow set of bases.
- Gem upgrading/corrupting in batches (quality + level + vaal outcomes).
- Recombination (if available in league) as a production process.

### 4.7 Commodity printing loops (low-friction farming → bulk sell)

Choose mechanics whose outputs are:
- stackable,
- always in demand,
- easy to liquidate.

Your DB should score mechanics by:
- average commodity value per run,
- inventory friction,
- time-to-liquidate.

### 4.8 Service economy (optional)

Examples:
- Boss carries,
- 5-way Legion,
- crafting services.

These can be profitable but are not “low effort”. Model them separately.

---

## 5) “All mechanics” checklist (tradable outputs to model)

This section is explicitly about what to treat as first-class commodities in your DB.

Reference list of core/extra mechanics (includes removed mechanics list):  
https://www.poewiki.net/wiki/League_mechanics

### 5.1 Atlas / endgame fundamentals (not a league mechanic, but drives trade)

Tradable outputs:
- Maps (esp. early atlas completion demand)
- Scarabs
- Invitations & fragments (boss access)
- Eldritch currencies (ichors/embers + related crafting items)
- Maven / Eater / Exarch / Uber fragments (patch-dependent)
- Scouting Reports (Kirac-related; some are Currency Exchange eligible)

### 5.2 Abyss

Outputs:
- Abyssal jewels (roll-dependent liquidity)
- Stygian Vise bases
- Abyss-related uniques

DB notes:
- Treat abyssal jewels like “semi-commodities”: classify by key mods and price bands.

### 5.3 Affliction (Viridian Wildwood)

Outputs (patch-dependent, verify each league):
- Affliction-specific items and uniques
- Anything that persists as a tradable item class (if present)

DB note:
- Treat as “event loot”: high variance, price sensitive to availability.

### 5.4 Ambush (Strongboxes)

Outputs:
- Divination cards (box-specific drops)
- Currency / scarabs / maps
- Strongbox-related scarabs and compounding strategies (if available)

Low-effort angle:
- Very low decision overhead; mostly “click and go”.

### 5.5 Anarchy (Rogue Exiles)

Outputs:
- Mostly generic drops; low direct commoditisation.

DB note:
- Usually model as “quantity/rarity juice” rather than a separate commodity.

### 5.6 Bestiary (Menagerie)

Outputs:
- Itemised beasts (specific beast types are the real market)
- Beastcraft outcomes (imprint/split/aspect/etc., depending on current game)

DB notes:
- Build an explicit “beast taxonomy” table keyed by beast name and craft category.
- Liquidity varies wildly by beast.

### 5.7 Betrayal (Immortal Syndicate)

Outputs:
- Veiled currency items (patch-dependent)
- Scarabs and other safehouse rewards
- Crafted outputs from benches (value-add)

DB notes:
- Bench crafts act like “embedded options”: you convert time/board state into tradable outputs.

### 5.8 Beyond / Scourge-style demon content (if present)

Outputs:
- Tainted currencies (if they drop in current version)
- Beyond uniques / boss drops (if applicable)

DB note:
- Verify per league/patch (availability changes historically).

### 5.9 Blight

Outputs:
- Oils (tiered)
- Blighted maps / Ravaged maps
- Blight uniques (if relevant)

DB notes:
- Oils are a clean commodity market; good for bulk liquidation.

### 5.10 Breach

Outputs:
- Splinters → breachstones
- Breach uniques
- Breach-related currencies/fragments (patch-dependent)

DB note:
- Splinter-to-stone conversion is a deterministic “processing” step.

### 5.11 Delirium

Outputs:
- Delirium orbs
- Simulacrum splinters
- Cluster jewels (value in notables)

DB notes:
- Cluster jewels need feature extraction (notables) + liquidity modelling.

### 5.12 Delve

Outputs:
- Fossils (type/tier)
- Resonators
- Boss drops (situational)

DB notes:
- Fossil markets are good for both farming and crafting loops.

### 5.13 Domination (Shrines)

Outputs:
- Mostly indirect (more monsters/speed), not its own commodity set.

### 5.14 Essence

Outputs:
- Essences by type/tier
- Corruption-related items (e.g., Remnant of Corruption, if present)

DB note:
- Pure commodity. One of the easiest markets to model.

### 5.15 Expedition

Outputs:
- Logbooks (by faction/mods)
- Reroll currencies and artifacts
- Rog-crafted items (sell-ready)
- Tujen deal conversions (turn into bulk currency)

DB notes:
- Logbooks are semi-commodities; classify by faction and key reward mods.

### 5.16 Harbinger

Outputs:
- Harbinger currency shards (including high-value shard types, patch-dependent)
- Ancient/Annulment/Fracturing-related shard economies (if present)

DB note:
- Often behaves like “slow lottery” with occasional spikes; needs large sample sizes.

### 5.17 Harvest

Outputs:
- Lifeforce (Wild/Vivid/Primal)
- Craft outputs (items) if you productise crafts

DB notes:
- Lifeforce is one of the best “stackable income streams”.
- Crafting with lifeforce is the “manufacturing” layer.

### 5.18 Heist

Outputs:
- Rogue’s Markers
- Contracts/Blueprints (by type/level)
- Heist-exclusive rewards (replicas, alt-quality gems, etc., if present)

DB note:
- Great if you can tolerate inventory; otherwise sell contracts/blueprints/markers in bulk.

### 5.19 Incursion

Outputs:
- Temples with valuable rooms (e.g., corruption-related rooms)
- Double-corrupted outcomes (high variance)

DB note:
- Temples are discrete “lots”; price by room set + tier.

### 5.20 Legion

Outputs:
- Splinters → emblems
- Timeless jewels
- Incubators
- 5-way economy (high effort, optional)

### 5.21 Rampage

Outputs:
- Mostly indirect; usually not a trade market.

### 5.22 Ritual

Outputs:
- Blood-filled vessels
- Deferred high-value items (manual judgement)

DB note:
- Hard to automate; treat as a “manual intervention” stream unless you only liquidate vessels.

### 5.23 Sanctum

Outputs (patch-dependent):
- Tomes / entry items (if applicable)
- Sanctum-specific uniques/currencies
- Relics (if tradable in current version)

DB note:
- High variance but can be extremely profitable; may not be “low effort”.

### 5.24 Sentinel

Outputs (if present):
- Sentinel items + components (if still obtainable)
- Any sentinel-only reward items

### 5.25 Settlers / Kingsmarch (if present in current league economy)

Potential outputs (verify per patch):
- Tattoos / runegrafts
- Recombinator-related outcomes
- Shipping/resource outputs if they become tradable

DB note:
- Treat town management as a separate production system if it exists.

### 5.26 Tempest / Torment / Warbands

Usually indirect or low-structure outputs. Model as “extra monsters/loot multipliers”.

### 5.27 Ultimatum

Outputs:
- Inscribed Ultimatums (if present)
- Ultimatum-specific rewards/currencies (patch-dependent)

---

## 6) Low-effort “productised” craft loops to backtest

The goal is to minimise judgement. Write acceptance rules so strict that crafting becomes mechanical.

### 6.1 Essence rares (batch crafting)

Loop:
1) Buy base types in bulk (correct ilvl).
2) Spam a single essence type.
3) Keep only items that meet a strict rule set.
4) Price in tiers and list async.

Acceptance rule examples:
- Life (>= threshold) AND total resists >= threshold AND open suffix/prefix condition.
- Movement speed boots with life + res.
- Reservation efficiency / suppression thresholds depending on meta.

DB requirements:
- Parse mods into a structured schema.
- Compute “feature vector” → price band mapping.

### 6.2 Gem manufacturing (batch)

Loops to test:
- Buy cheap 20-quality gems → level → vaal in batches → sell 21/20 outcomes.
- Buy underpriced awakened gems early → hold until peak demand.

DB requirements:
- Track gem level/quality/corruption state.
- Track price distribution by outcome.

### 6.3 Fossil crafting narrow bases

Only worth it if you:
- pick one base with constant demand,
- pick one fossil set,
- sell only high-liquidity outcomes.

DB requirements:
- Base classification (influence/fractured/synth, ilvl).
- Outcome scoring rules.

### 6.4 Recombination (if available)

Treat as:
- Inputs → probabilistic merge → outputs.

DB requirements:
- Define “input cost”.
- Estimate output distribution from your own observed outcomes (even if noisy).
- Only run if expected value beats liquidation.

---

## 7) Backtesting framework improvements (what to add beyond “median price”)

### 7.1 Normalise prices and costs

- Choose a base currency (divine or chaos).
- Always include **gold** as a constraint/cost where relevant (Currency Exchange; async buy tax affects demand).

### 7.2 A realistic sell model (most important refinement)

You need to avoid fake profits from “I can always sell at mid”.

For each item class, estimate:
- probability of sale within T hours at a given relative price,
- expected time-to-sell,
- cancellation/delist probability.

Data sources:
- Your own listing history (best)
- Public stash delistings (noisy proxy)

### 7.3 Venue-specific execution simulation

Currency Exchange:
- maker vs taker fills
- partial fills
- gold cost per order (and non-refund behaviour)

Async items:
- listing delay + repricing cooldown constraints
- buyer gold tax likely suppresses ultra-cheap item demand

Manual:
- attention cost (whispers/time)
- “fail to trade” rate (ignored whispers, etc.)

### 7.4 Strategy evaluation metrics

Store per strategy + time window:
- gross profit, net profit
- profit per attention-minute
- turnover (inventory velocity)
- max drawdown
- liquidity (median time-to-sell)

### 7.5 Opportunity detectors (alerts your DB can generate)

Currency Exchange:
- high-volume pairs where spread widens abnormally
- volatility breaks (regime shift)

Async listings:
- items in your stash with unusually high price spikes vs last week
- items you have duplicates of that have low listing competition

Craft loops:
- input basket cost drops below threshold while output prices stay stable

---

## 8) Prioritised research backlog (high impact first)

1) **Add async trading economics to your models.**  
   Buyer gold tax + repricing cooldowns change what sells and how you should price.

2) **Expand the “mechanics outputs” mapping to full coverage.**  
   Use the PoE wiki mechanics list as the starting index, then add per-mechanic “trade outputs”.

3) **Build a gold-aware Currency Exchange simulator.**  
   Model gold as a limited budget, and compute profit per gold spent.

4) **Implement time-to-sell modelling.**  
   Without this, low-effort optimisation is impossible (you’ll overfit to theoretical prices).

5) **Add endgame boss fragment and invitation markets.**  
   These are often among the most liquid high-ticket markets mid league.

6) **Add gem + div card markets.**  
   Div cards are also explicitly tradable on Currency Exchange (eligible categories include divination cards).

7) **Meta-demand modelling.**  
   Use poe.ninja build distributions to predict item demand spikes.

---

## 9) Suggested DB schema additions (beyond your current stash sync)

Core tables:
- `league(id, name, start_at, end_at, realm)`
- `item(id, hash, base_type, item_class, ilvl, rarity, influences..., fractured, synthesised, corrupted, …)`
- `own_stash_snapshot(ts, league_id, tab_id, item_id, stack_size, location)`

Market data:
- `public_listing_observation(ts, listing_id, item_id, seller, price, league_id, source)`
- `cx_hour(ts_hour, league_id, market_id, volume_traded_json, lowest_ratio_json, highest_ratio_json, lowest_stock_json, highest_stock_json)`  
  (matches official `/currency-exchange` fields)

Trading execution (optional but extremely valuable):
- `own_listing(id, item_id, venue, listed_at, price_currency, price_amount)`
- `own_sale(id, own_listing_id, sold_at, received_currency, received_amount)`
- `gold_ledger(ts, league_id, delta_gold, reason)`  
  (estimate gold constraints; even if you can’t read it directly, track via manual input or inferred budgets)

Derived views:
- `v_liquidity(item_id, league_id)`: time-to-sell, sell-through, cancel rate
- `v_price(ts_bucket, item_id)`: median/p10/p90/volume
- `v_strategy_pnl(strategy_id, ts_bucket)`

---

## Appendix A: League calendar notes (as of Feb 23, 2026)

- 3.27 expansion announced for Oct 31, 2025 (PDT): https://www.pathofexile.com/forum/view-thread/3865111  
- 3.28 timeline update: reveal Feb 26, 2026 (11AM PST), launch March 6, 2026 (11AM PST): https://www.pathofexile.com/forum/view-thread/3911341

For automation: prefer the `/league` API’s `startAt/endAt` over hardcoding dates.


---

## Appendix B: Community research + profitability datasets (where to pull data)

This appendix is a curated index of **data-heavy community sources** you can ingest to model profitability of mechanics and services. The goal is not to “copy” their conclusions, but to **import their raw datasets (or published tables)** into your own pipeline.

General ingestion pattern (recommended):
- Store `source_name`, `source_url`, `retrieved_at`, `league`, `patch`, plus the **raw payload** (CSV/JSON/HTML snapshot).
- Parse into “typed” tables with a stable schema.
- Keep a **mapping layer** (name normalisation + ID mapping) because community display names change.

### B.1 Prohibited Library (PoE Science & Data Collection)

What it is: a research-focused community that publishes datasets (usually Google Sheets) on drop weights, mechanic probabilities, and economic EV components.

Primary hub:
- Discord invite (as referenced in their digest): https://discord.gg/3VxKY6gt7j

High-value public datasets to ingest:

1) **Divination card weights (natural drops)**
- Digest thread (context + caveats):  
  https://www.reddit.com/r/pathofexile/comments/wsi0j8/complete_divination_card_dropweight_tables_drop/
- Public sheet (“Estimated Divination Card Weights, Natural Drops | 3.18 Sentinel League | Prohibited Library”):  
  https://docs.google.com/spreadsheets/d/1n6h0IBy8byU869nLoXlwrFmxjSHMVtYlNhePrEtJcLQ/edit?usp=sharing
- Key fields (typical): `version`, `card_name`, `estimated_weight`, `notes`.

Direct uses in your system:
- EV of **Stacked Decks** (requires a separate Stacked Deck outcome distribution; their Discord has large pull datasets).
- EV of targeted “area card” farming (weights help sanity-check location hypotheses).
- “League-phase priors” for card scarcity/availability.

2) **Outcome probabilities for *The Void* card**
- Public sheet:  
  https://docs.google.com/spreadsheets/d/1COtTCmENr7KXELL7KPUVJgoNsDpTIEMOl6wDFUrp1e4/edit?usp=sharing

Direct uses:
- EV of buying/selling *The Void* at different price points (variance modelling).

3) **Player IIQ diminishing returns (usable formula)**
- Digest thread (contains formula + explanation):  
  https://www.reddit.com/r/pathofexile/comments/wsi0j8/complete_divination_card_dropweight_tables_drop/

Prediction function (for playerIIQ >= 0):
- `incrementalDropMultiplier = 0.888 * (1 - exp(-playerIIQ))`
- `naturalDropMultiplier = 1 + incrementalDropMultiplier`

Precomputed reference table (derived from the formula above; rounding to 2 decimals):

|   Player IIQ % | Estimated natural drop multiplier   | Benefit vs prev +10%   |
|---------------:|:------------------------------------|:-----------------------|
|              0 | 1.00x                               |                        |
|             10 | 1.08x                               | 8.45%                  |
|             20 | 1.16x                               | 7.05%                  |
|             30 | 1.23x                               | 5.96%                  |
|             40 | 1.29x                               | 5.09%                  |
|             50 | 1.35x                               | 4.38%                  |
|             60 | 1.40x                               | 3.80%                  |
|             70 | 1.45x                               | 3.31%                  |
|             80 | 1.49x                               | 2.90%                  |
|             90 | 1.53x                               | 2.55%                  |
|            100 | 1.56x                               | 2.25%                  |
|            110 | 1.59x                               | 1.99%                  |
|            120 | 1.62x                               | 1.77%                  |
|            130 | 1.65x                               | 1.57%                  |
|            140 | 1.67x                               | 1.40%                  |
|            150 | 1.69x                               | 1.25%                  |
|            160 | 1.71x                               | 1.12%                  |
|            170 | 1.73x                               | 1.00%                  |
|            180 | 1.74x                               | 0.89%                  |
|            190 | 1.75x                               | 0.80%                  |
|            200 | 1.77x                               | 0.72%                  |
|            210 | 1.78x                               | 0.65%                  |
|            220 | 1.79x                               | 0.58%                  |
|            230 | 1.80x                               | 0.52%                  |
|            240 | 1.81x                               | 0.47%                  |
|            250 | 1.81x                               | 0.42%                  |
|            260 | 1.82x                               | 0.38%                  |
|            270 | 1.83x                               | 0.34%                  |
|            280 | 1.83x                               | 0.31%                  |
|            290 | 1.84x                               | 0.28%                  |
|            300 | 1.84x                               | 0.25%                  |

Direct uses:
- Convert MF investment into an estimated multiplier for **natural drops** (important caveat: does not apply to many deterministic reward systems).

4) **Heist blueprint Curio Case reward distribution**
- Reddit thread:  
  https://www.reddit.com/r/pathofexile/comments/1f22j01/heist_blueprint_curio_case_reward_data_324/
- Public sheet:  
  https://docs.google.com/spreadsheets/d/1dDDMRc3GAE4G0XTNm3nOv4UxT2e_RduzoBNcDdyPFrs/edit?usp=sharing

Direct uses:
- EV of running vs selling blueprints (by type/wings/curio assumptions).
- Identify when “sell blueprint” beats “run blueprint” under current prices.

5) **Incursion (Alva) Temple room weights (starting-state sampling)**
- Reddit thread:  
  https://www.reddit.com/r/pathofexile/comments/1cbf9sr/alva_temple_room_science_we_need_your_temples/
- Public sheet:  
  https://docs.google.com/spreadsheets/d/1Idt5trrS_x2FbDq3ldjj4HnLYCBltZKi2SSQ7jYSxyM/edit?usp=sharing

Direct uses:
- Simulate “probability of producing Locus/Doryani” under different play patterns.
- EV of buying/selling Incursion Scarabs / Alva compasses if you model room generation.

Ingestion notes (Google Sheets):
- Future workers should pull as CSV via:  
  `https://docs.google.com/spreadsheets/d/<SHEET_ID>/export?format=csv&gid=<GID>`  
  (or `gviz/tq?tqx=out:csv`).
- Store `gid` per tab so schema changes don’t silently corrupt pipelines.

### B.2 The Forbidden Trove (TFT) pricing datasets (services + bulk)

What it is: the most widely used community venue for **services and bulk trade**. They publish aggregated price outputs.

Primary dataset:
- GitHub repo: https://github.com/The-Forbidden-Trove/tft-data-prices  
  (linked from `http://data.tftrove.com` in the README)

What it contains (examples; see README for the full list):
- **Services** (Betrayal benchcrafts, Temple benchcrafts)
- **Compasses** (Sextant mods)
- **Heist contracts**
- Other bulk prices

Operational notes from TFT (important for ingestion stability):
- Timestamps are **epoch time** (JavaScript `Date.now()` format).
- Display names and file paths may change; they recommend following their Discord `#tool-dev-updates`.

TFT Discord:
- Join: http://discord.tftrove.com

Direct uses in your system:
- Price “service outputs” for strategies where your own stash data cannot reveal the *price of the service* (Aisling, Locus, etc.).
- Evaluate compasses and bulk deals that the Currency Exchange does not cover well.
- Build “should I sell this as a service vs as an item?” models.

Ingestion suggestion:
- Treat TFT price feeds as **external market venues** with their own price curves.
- Normalise by category (`services_betrayal`, `services_temple`, `compass_mods`, `bulk_heist`, …).
- Keep a `name_mapping` table because TFT display names are not guaranteed stable.

### B.3 poe.ninja APIs + data dumps (economy backbone)

Key idea: poe.ninja remains the most convenient public price source for league items, and it has both **live endpoints** and **historical league dumps**.

API endpoints (community-documented; examples):
- Currency overview:  
  `https://poe.ninja/api/data/currencyoverview?league=<LEAGUE>&type=Currency`
- Item overview:  
  `https://poe.ninja/api/data/itemoverview?league=<LEAGUE>&type=<TYPE>`  
  Example types commonly used: `UniqueWeapon`, `UniqueArmour`, `UniqueAccessory`, `UniqueFlask`, `UniqueJewel`, `SkillGem`, `Map`, `Beast`, etc.

Community references (handy for future workers):
- r/pathofexiledev: currencyoverview example endpoint:  
  https://www.reddit.com/r/pathofexiledev/comments/eduo3d/pulling_currency_from_poeninja/
- r/pathofexiledev: list of itemoverview endpoints/types:  
  https://www.reddit.com/r/pathofexiledev/comments/d9ubuv/poeninja_api/
- API doc repo (unofficial):  
  https://github.com/ayberkgezer/poe.ninja-API-Document

Data dumps / historical:
- poe.ninja “Data” page: https://poe.ninja/poe1/data  
- A community forum post quotes the “Data dumps” description and notes zips per league timespan:  
  https://www.pathofexile.com/forum/view-thread/3867005

Direct uses:
- Price curves for anything you can buy/sell.
- “League phase priors” (day 1 vs week 3 behaviour).
- Training data for your own liquidity models.

### B.4 PoE Antiquary (historical prices UI built on poe.ninja)

- Site: https://poe-antiquary.xyz/
- Purpose (per site): compare prices from past SC/HC challenge leagues, create custom graphs, and browse item tables; data provided by poe.ninja.

Direct uses:
- Fast manual validation of “what typically rises/falls” by day count.
- Cross-league backtests when you don’t want to ingest full dumps yet.

### B.5 Poe Atlas Data API (pre-packaged JSON price files)

- API hub: https://data.poeatlas.app/
- Claims: provides league-specific JSON price files (e.g., delirium orb prices) updated automatically (example text indicates every ~3 hours).

Direct uses:
- If you want “ready-to-ingest JSON per category per league” without dealing with poe.ninja schema drift.

### B.6 Profit calculators / EV tooling (open and scriptable)

1) **poe-profits.com (bossing / gem levelling / Harvest rerolls)**
- Site: https://poe-profits.com/
- GitHub: https://github.com/Kazanir/poe-profits  
  Notes from repo: drop rates are editable in code; price sources include poe.watch/poe.ninja; gem list references PoEGems and PoE Wiki.

2) **exile-profit (scripts + generated outputs)**
- GitHub: https://github.com/Vyary/exile-profit  
  Positioning: “A set of scripts to show profit for Path of Exile” with an auto-updating Google Sheet; the repo contains scripts and generated outputs.

3) **LootCalc (PoE currency profit & map returns calculators)**
- Site hub: https://lootcalc.com/ (see “PoE Currency Profit & Map Returns”)

How to use these responsibly:
- Treat them as a “second opinion” and a way to validate your own EV computations.
- Prefer ingesting raw inputs (drop rates, reward tables, prices) rather than copying their final profit numbers.

### B.7 Personal wealth / session tracking tools (for benchmarking your own pipeline)

These tools often have **exportable snapshots** and can be used as a sanity check against your DB results.

- Exilence Next (desktop app; wealth over time + hourly basis):  
  https://github.com/viktorgullmark/exilence-next

- Wealthy Exile (web app; stash tracking, currency/hour, snapshots):  
  https://wealthyexile.com/  
  CSV export is referenced by tools that parse WealthyExile exports (example):  
  https://www.reddit.com/r/pathofexile/comments/1pyyz5r/tools_poe_stash_regex_generator_poe_currency/

- PoeStack (pricing + selling helper; bulk-aware pricing approach):  
  Dev blog on their pricing approach (no GGG trade search calls):  
  https://medium.com/@PoeStack/poestack-dev-blog-1-determining-value-in-a-subjective-economy-4e415623c495  
  (Also see their subreddit announcement for feature overview):  
  https://www.reddit.com/r/pathofexile/comments/10qwuxz/poestack_stock_based_pricing_manual_pricing/

### B.8 Developer/tooling reference lists (mods, affixes, IDs)

For tool-building, you often need mod IDs, spawn weights, and canonical naming.

- PoEDB “development tool site” index (includes Official API, PoE API collection, PyPoE, RePoE links):  
  https://poedb.tw/ru/markdown_raw?oldid=7475
- RePoE (large repository of resources for tool developers):  
  https://github.com/brather1ng/RePoE/
- Awakened PoE Trade (price-checking app; references RePoE/poe.ninja in acknowledgments):  
  https://github.com/SnosMe/awakened-poe-trade

---

### B.9 Practical “next ingestion” shortlist

If you only ingest 5 external sources, do these first:

1) TFT `tft-data-prices` (service + bulk pricing): `tft-data-prices`
2) Prohibited Library div card weights + IIQ formula
3) Prohibited Library Heist blueprint Curio Case rewards
4) poe.ninja API (currencyoverview + key itemoverview categories)
5) poe.ninja data dumps (for historical league phase modelling) or PoE Antiquary if you prefer UI first
