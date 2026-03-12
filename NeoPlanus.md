# Path of Exile Trading Intelligence Platform

## Refined, simplified, ClickHouse-first implementation plan

This is the refined version of the plan after re-checking your current repo, the current PoE developer docs, and the newer `service:cxapi` scope. The previous version was too complex in a few places. The right shape is much simpler:

* one private sync daemon
* one database: ClickHouse
* one interface layer: CLI first, optional TUI later
* SQL as the main implementation language for analytics
* Python only for API polling, scheduling, orchestration, and the few strategy evaluators that are genuinely awkward in SQL
* no Redis
* no Postgres
* no Web UI
* no generic ETL framework
* no custom strategy DSL

The official constraints matter here. Public Stashes are a realm-wide stream with an official ~5 minute delay, and Currency Exchange is an hourly historical stream with no current-hour data. `service:*` scopes are not available to public OAuth clients, and GGG only supports endpoints defined in the official API reference. That combination strongly favors a private backend-style daemon, ClickHouse-native transforms, and a design centered on delayed intelligence and research rather than instant sniping. ([Path of Exile][1])

---

## 1. Final design decisions

### 1.1 The architecture is now intentionally boring

The system should be:

`PoE APIs -> one sync daemon -> ClickHouse bronze -> ClickHouse silver/gold SQL models -> scanner/backtests -> CLI/TUI`

That is it.

There should be no dbt, no Airflow, no Dagster, no Kafka, no Redis cache, no Postgres metadata store, and no separate “ETL service.” The database is already ClickHouse, and ClickHouse is fully capable of doing the parsing, flattening, aggregation, bucketing, and most of the strategy math.

### 1.2 Python is orchestration, not the analytics engine

Keep Python 3.11 because it is easy to maintain and your existing repo is already Python. Use Python for:

* OAuth token refresh
* API polling loops
* executing SQL model files
* scheduling refreshes
* rendering terminal reports
* optional advanced craft/corruption EV logic when SQL becomes ugly

Do not implement a large Python-side normalization pipeline if ClickHouse can express the logic directly.

### 1.3 No custom DSL in v1

A full strategy DSL is not justified yet.

Instead, each strategy should be a small package:

* `strategy.toml` for metadata and thresholds
* `discover.sql` for candidate generation
* `backtest.sql` for historical evaluation
* `notes.md` for human explanation
* optional `eval.py` only for advanced stochastic logic

That is much easier for humans and coding agents to maintain than inventing a mini-language.

### 1.4 ClickHouse is the single source of truth

Move as much state as possible into ClickHouse:

* raw API data
* checkpoint history
* request logs
* current-state views
* strategy results
* scanner alerts
* execution journal

The current file-backed checkpoints are simple, but they are still unnecessary extra state outside the database. That should be removed.

### 1.5 CLI first, TUI second

The research value is in the engine, not in the interface. A browser app would slow the project down for little gain.

The right order is:

1. CLI
2. markdown / JSON reports
3. optional TUI with `rich` or `textual`

Bulky is a good proof that a focused trading tool does not need a full web product to be useful. Its differentiators are category handling, regex-driven map trading, fragment sets, and logbook handling, not a giant UI. ([Path of Exile][2])

---

## 2. What is wrong or overly complex in the current shape

Your repo is already a solid ingestion base, but a few things should be changed immediately.

### 2.1 Public Stash ingestion should not be `realm × league`

Your current harvester loops across `realm × league`, and sends `league` in the Public Stash request params. The current official docs define Public Stashes as:

* `GET /public-stash-tabs[/<realm>]`
* optional query param: `id`
* stream contains **all public stashes in all leagues for the given realm**
* results are delayed by about 5 minutes ([Path of Exile][1])

So the current multi-league PSAPI topology is the wrong abstraction. It risks wasted requests, confusing checkpoints, and possibly duplicate ingestion if the upstream ignores the undocumented `league` parameter.

**Fix:** one PSAPI queue per realm, filter leagues locally after ingest.

### 2.2 The current code relies on file checkpoints even though ClickHouse already stores checkpoint history

You already write `bronze_ingest_checkpoints`. That should become the canonical checkpoint source. File checkpoints are redundant.

**Fix:** remove runtime dependence on `CheckpointStore`; load the latest successful checkpoint from ClickHouse at startup and after each batch.

### 2.3 The repo still contains logic for an undocumented trade metadata path

Current code calls `api/trade/data/<cursor>` and older views depend on that. The official developer docs say they only support resources defined in the API reference or data exports, and requests for other internal website APIs will be denied. ([Path of Exile][3])

That means this trade-metadata path should not be part of the core design.

**Fix:** deprecate it. Leave the old table in place only for compatibility if needed, but do not depend on it for v2.

### 2.4 The old silver/gold plan was too framework-shaped

The repo contains old docs talking about bronze/silver/gold plus ETL services, analytics services, UI layers, and broader scope. But `0018_cleanup_unused_objects.sql` explicitly dropped many of those older analytics tables and views. The live repo is much closer to:

* bronze ingest
* request/checkpoint telemetry
* minimal ops/status

So v2 should not pretend a full analytics stack already exists. It should add a new ClickHouse-native analytics layer cleanly and incrementally.

### 2.5 The existing `raw_currency_exchange_hour` design should not be restored as-is

The current official Currency Exchange endpoint is:

* `GET /currency-exchange[/<realm>][/<id>]`
* `id` is a unix timestamp truncated to the hour
* response is hourly historical only
* there is no current-hour data
* each response contains `markets`, and each market includes `league` and `market_id` inside the payload ([Path of Exile][1])

So a bronze CX row should be keyed by realm and requested hour, not by a single league column at the raw level.

---

## 3. The external constraints that must shape the implementation

### 3.1 Public Stash is delayed and realm-wide

Public Stashes are PoE1-only, realm-wide, and delayed. A stash can reappear in the stream and if a stash becomes unlisted, all details except `id` and `public` may be omitted. If the returned `stashes` array is empty, you are at the end of the current stream and should poll the same `next_change_id` later. ([Path of Exile][1])

Implications:

* do not build the whole project around “instant” sniping
* current-state modeling must be stash-snapshot-aware
* disappearance heuristics will always be proxies, not explicit fills
* PSAPI is excellent for medium-speed and delayed edges, not for zero-latency edges

### 3.2 Currency Exchange is historical hourly data, not live order book depth

Currency Exchange responses are grouped into hourly digests. There is no way to get the current hour. If `next_change_id` equals the hour you requested, you are already at the current end and should wait for the next hour boundary. If no `id` is provided, the endpoint assumes the first hour of history. ([Path of Exile][1])

Implications:

* CXAPI is ideal for normalization, volatility, liquidity regime analysis, and historical market-making research
* it is not a live execution feed
* the daemon must **never** call CXAPI without an explicit hour id unless it is doing an intentional full-history backfill

### 3.3 `service:*` scopes imply a private backend-style tool

GGG’s OAuth docs say public clients cannot use `service:*` scopes, while confidential clients can use any grant types and typically have separate client-level rate limits. The general developer guidance also says they only support standalone apps and websites that stay separate from the game, and reading log files is okay only if the user is aware of it. ([Path of Exile][4])

Implications:

* keep this as a private daemon you run yourself
* do not distribute a desktop binary with embedded secrets
* do not design this like a public-client consumer tool
* optional `Client.txt` ingestion is allowed only as an explicit opt-in

### 3.4 Merchant Tabs and Currency Exchange are different sale venues

The official Asynchronous Trade FAQ says Merchant Tabs cannot sell currency items, buyers pay a gold cost to buy from a Merchant Tab, and there is a cooldown on removing or repricing listed items. Patch 3.27 also explicitly mentions reduced gold fees for many basic Currency Exchange items, which confirms that exchange-side friction is part of the market structure too. ([Path of Exile][5])

Implications:

* execution venue must be part of every strategy
* currency-like strategies should point to Currency Exchange
* item-like strategies should point to manual trade or Merchant Tabs
* low-ticket item strategies must consider venue friction and buyer behavior

### 3.5 3.28 changed some market fundamentals

The 3.28 Mirage patch notes matter for strategy priority. Relevant changes include:

* fossils removed from non-Delve sources, with Delve fossil frequency increased
* Tujen no longer selling Cluster Jewels or Abyss Jewels
* Kingsmarch shipping changes and new reward routes
* Kingsmarch mappers no longer returning cluster jewels over item level 83 ([Path of Exile][6])

Implications:

* fossil and resonator markets deserve first-class tracking
* Rog gets relatively more interesting because high item-level base supply shifts
* cluster-jewel valuation should be re-checked with current league data, not just historical assumptions

---

## 4. The simplified target architecture

The system should have only five logical layers.

### 4.1 Sync daemon

One private daemon process, reusing your existing `market_harvester` entrypoint, but internally refactored into two queues:

* `psapi:<realm>`
* `cxapi:<realm>`

No thread pool per league. No parallel worker farm. One scheduler loop is enough.

### 4.2 Bronze

Append-only raw API storage plus request/checkpoint telemetry.

### 4.3 Silver

Mostly ClickHouse-native flattened tables and enriched views:

* explode raw stash changes into stash rows and item rows
* explode raw currency exchange hours into market rows
* parse price notes, categories, and core item fields
* derive current-state views

### 4.4 Gold

Reference marts and research tables:

* currency normalization
* listing price refs
* liquidity refs
* bulk premium refs
* set assembly refs
* strategy backtests
* scanner recommendations

### 4.5 CLI / optional TUI

The user-facing tool reads from gold views/tables and tells you:

* which strategy fired
* which item or market to buy
* max price / spread
* what transform to apply
* where to sell it
* expected profit
* expected hold time
* confidence

That is enough to make the system useful.

---

## 5. The core simplifications compared to the earlier plan

### 5.1 No ETL framework

Use only three ClickHouse-native patterns:

1. **Materialized views** for raw -> exploded silver rows
2. **Regular views** for enriched / current-state logic
3. **Scheduled SQL refreshes** for gold tables and research outputs

That is the whole transformation story.

### 5.2 No custom DSL

Use plain SQL plus tiny metadata files.

The strategy system is:

* metadata in `strategy.toml`
* candidate discovery in `discover.sql`
* historical evaluation in `backtest.sql`
* optional Python evaluator for advanced stochastic transforms only

SQL is already the strategy language. Do not invent another one.

### 5.3 No file checkpoints

Use `bronze_ingest_checkpoints` as the canonical cursor log.

### 5.4 No Web UI

Use:

* terminal tables
* markdown reports
* JSONL
* optional TUI later

### 5.5 No external pricing dependency in the core path

With `service:cxapi`, the core system can use official exchange history for currency normalization and regime detection. External sites can stay optional and out-of-band.

---

## 6. Concrete ClickHouse design

## 6.1 Keep and reuse existing bronze tables

Keep these, with only additive alterations where needed:

* `poe_trade.raw_public_stash_pages`
* `poe_trade.bronze_ingest_checkpoints`
* `poe_trade.bronze_requests`
* `poe_trade.poe_ingest_status`

Recommended adjustments:

* make `league` nullable in ops/bronze status tables if it is not already
* add `queue_key` so checkpoint queries are trivial
* keep raw JSON compressed
* keep timestamp delta codecs

`raw_public_stash_pages` should remain, but document clearly that it stores one **PublicStashChange** per row, not a literal full page payload.

## 6.2 Re-add Currency Exchange bronze with a corrected schema

Do **not** recreate the old raw CX table exactly as it was. The bronze row should be one full hourly response for one realm and one requested hour.

Recommended table:

```sql
CREATE TABLE IF NOT EXISTS poe_trade.raw_currency_exchange_hour (
    recorded_at DateTime64(3, 'UTC') CODEC(Delta, ZSTD(1)),
    realm LowCardinality(String),
    requested_hour DateTime64(0, 'UTC') CODEC(Delta, ZSTD(1)),
    next_change_id UInt64,
    payload_json String CODEC(ZSTD(6))
)
ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(requested_hour)
ORDER BY (realm, requested_hour)
TTL recorded_at + INTERVAL 365 DAY;
```

Why this shape is correct:

* one request is for one realm and one hour
* response includes multiple leagues inside `markets`
* `next_change_id` is a unix-hour cursor, not an item cursor ([Path of Exile][1])

## 6.3 Silver: stash-change header rows

Add a narrow table or MV for stash-level facts.

```sql
CREATE TABLE IF NOT EXISTS poe_trade.silver_ps_stash_changes (
    observed_at DateTime64(3, 'UTC'),
    realm LowCardinality(String),
    league Nullable(String),
    stash_id String,
    public_flag UInt8,
    account_name Nullable(String),
    stash_name Nullable(String),
    stash_type Nullable(String),
    checkpoint String,
    next_change_id String,
    payload_json String
)
ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(observed_at)
ORDER BY (realm, stash_id, observed_at);
```

Materialized view from bronze:

```sql
CREATE MATERIALIZED VIEW IF NOT EXISTS poe_trade.mv_ps_stash_changes
TO poe_trade.silver_ps_stash_changes
AS
SELECT
    ingested_at AS observed_at,
    realm,
    league,
    stash_id,
    toUInt8(ifNull(JSONExtractBool(payload_json, 'public'), 1)) AS public_flag,
    nullIf(JSONExtractString(payload_json, 'accountName'), '') AS account_name,
    nullIf(JSONExtractString(payload_json, 'stash'), '') AS stash_name,
    nullIf(JSONExtractString(payload_json, 'stashType'), '') AS stash_type,
    checkpoint,
    next_change_id,
    payload_json
FROM poe_trade.raw_public_stash_pages;
```

## 6.4 Silver: exploded item rows

Add a second MV to explode items from each stash change.

```sql
CREATE TABLE IF NOT EXISTS poe_trade.silver_ps_items_raw (
    observed_at DateTime64(3, 'UTC'),
    realm LowCardinality(String),
    league Nullable(String),
    stash_id String,
    public_flag UInt8,
    account_name Nullable(String),
    stash_name Nullable(String),
    stash_type Nullable(String),
    checkpoint String,
    next_change_id String,
    item_id Nullable(String),
    item_name String,
    item_type_line String,
    base_type String,
    rarity Nullable(String),
    ilvl UInt16,
    stack_size UInt32,
    note Nullable(String),
    forum_note Nullable(String),
    corrupted UInt8,
    fractured UInt8,
    synthesised UInt8,
    item_json String
)
ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(observed_at)
ORDER BY (realm, league, stash_id, observed_at, item_id);
```

Materialized view sketch:

```sql
CREATE MATERIALIZED VIEW IF NOT EXISTS poe_trade.mv_ps_items_raw
TO poe_trade.silver_ps_items_raw
AS
SELECT
    base.ingested_at AS observed_at,
    base.realm,
    base.league,
    base.stash_id,
    toUInt8(ifNull(JSONExtractBool(base.payload_json, 'public'), 1)) AS public_flag,
    nullIf(JSONExtractString(base.payload_json, 'accountName'), '') AS account_name,
    nullIf(JSONExtractString(base.payload_json, 'stash'), '') AS stash_name,
    nullIf(JSONExtractString(base.payload_json, 'stashType'), '') AS stash_type,
    base.checkpoint,
    base.next_change_id,
    nullIf(JSONExtractString(item_json, 'id'), '') AS item_id,
    JSONExtractString(item_json, 'name') AS item_name,
    JSONExtractString(item_json, 'typeLine') AS item_type_line,
    JSONExtractString(item_json, 'baseType') AS base_type,
    nullIf(JSONExtractString(item_json, 'rarity'), '') AS rarity,
    toUInt16(ifNull(JSONExtractInt(item_json, 'ilvl'), 0)) AS ilvl,
    greatest(1, toUInt32(ifNull(JSONExtractInt(item_json, 'stackSize'), 1))) AS stack_size,
    nullIf(JSONExtractString(item_json, 'note'), '') AS note,
    nullIf(JSONExtractString(item_json, 'forum_note'), '') AS forum_note,
    toUInt8(ifNull(JSONExtractBool(item_json, 'corrupted'), 0)) AS corrupted,
    toUInt8(ifNull(JSONExtractBool(item_json, 'fractured'), 0)) AS fractured,
    toUInt8(ifNull(JSONExtractBool(item_json, 'synthesised'), 0)) AS synthesised,
    item_json
FROM poe_trade.raw_public_stash_pages AS base
ARRAY JOIN JSONExtractArrayRaw(base.payload_json, 'items') AS item_json;
```

The official PublicStashChange includes `stash`, and the Item type includes `note` and `forum_note`, so the effective pricing signal should be built from those three fields in that order. ([Path of Exile][1])

## 6.5 Silver: enriched views, not more Python

Build enriched views rather than Python transforms for these:

* effective price note
* parsed price amount / currency
* category / subcategory
* links / sockets
* gem level / quality when needed
* cluster / flask / map / fragment / essence / fossil / scarab detection
* low-dimensional item signatures

Example:

```sql
CREATE VIEW poe_trade.v_ps_items_enriched AS
SELECT
    *,
    coalesce(note, forum_note,
        if(match(ifNull(stash_name, ''), '^~'), stash_name, NULL)
    ) AS effective_price_note,
    toFloat64OrNull(extract(effective_price_note, '^~(?:b/o|price)\\s+([0-9]+(?:\\.[0-9]+)?)')) AS price_amount,
    nullIf(extract(effective_price_note, '^~(?:b/o|price)\\s+[0-9]+(?:\\.[0-9]+)?\\s+(.+)$'), '') AS price_currency,
    multiIf(
        match(base_type, 'Essence'), 'essence',
        match(base_type, 'Fossil'), 'fossil',
        match(base_type, 'Scarab'), 'scarab',
        match(base_type, 'Cluster Jewel'), 'cluster_jewel',
        match(item_type_line, ' Map$'), 'map',
        match(base_type, 'Logbook'), 'logbook',
        match(base_type, 'Flask'), 'flask',
        'other'
    ) AS category
FROM poe_trade.silver_ps_items_raw;
```

This should stay intentionally narrow. Do **not** build a complete PoE item ontology in phase 1.

## 6.6 Current-state views should be stash-driven

Because a stash can reappear and can also become unlisted with most details omitted, current state should be derived from the latest stash snapshot per `stash_id`, not from naive “last seen item row” logic. ([Path of Exile][1])

Recommended views:

* `v_ps_current_stashes`
* `v_ps_current_items`

Sketch:

```sql
CREATE VIEW poe_trade.v_ps_current_stashes AS
SELECT
    stash_id,
    argMax(realm, observed_at) AS realm,
    argMax(league, observed_at) AS league,
    argMax(public_flag, observed_at) AS public_flag,
    argMax(account_name, observed_at) AS account_name,
    argMax(stash_name, observed_at) AS stash_name,
    max(observed_at) AS observed_at,
    argMax(payload_json, observed_at) AS payload_json
FROM poe_trade.silver_ps_stash_changes
GROUP BY stash_id;
```

Then explode items from only the latest `public_flag = 1` stash rows.

This view becomes the base for almost all scanner queries.

## 6.7 Silver: exploded Currency Exchange markets

Add a materialized view for hourly market rows.

```sql
CREATE TABLE IF NOT EXISTS poe_trade.silver_cx_markets_hour (
    recorded_at DateTime64(3, 'UTC'),
    realm LowCardinality(String),
    hour_ts DateTime64(0, 'UTC'),
    league String,
    market_id String,
    base_code String,
    quote_code String,
    volume_traded_json String,
    lowest_stock_json String,
    highest_stock_json String,
    lowest_ratio_json String,
    highest_ratio_json String
)
ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(hour_ts)
ORDER BY (realm, league, market_id, hour_ts);
```

Materialized view sketch:

```sql
CREATE MATERIALIZED VIEW IF NOT EXISTS poe_trade.mv_cx_markets_hour
TO poe_trade.silver_cx_markets_hour
AS
SELECT
    recorded_at,
    realm,
    requested_hour AS hour_ts,
    JSONExtractString(market_json, 'league') AS league,
    JSONExtractString(market_json, 'market_id') AS market_id,
    splitByChar('|', JSONExtractString(market_json, 'market_id'))[1] AS base_code,
    splitByChar('|', JSONExtractString(market_json, 'market_id'))[2] AS quote_code,
    coalesce(JSONExtractRaw(market_json, 'volume_traded'), '{}') AS volume_traded_json,
    coalesce(JSONExtractRaw(market_json, 'lowest_stock'), '{}') AS lowest_stock_json,
    coalesce(JSONExtractRaw(market_json, 'highest_stock'), '{}') AS highest_stock_json,
    coalesce(JSONExtractRaw(market_json, 'lowest_ratio'), '{}') AS lowest_ratio_json,
    coalesce(JSONExtractRaw(market_json, 'highest_ratio'), '{}') AS highest_ratio_json
FROM poe_trade.raw_currency_exchange_hour
ARRAY JOIN JSONExtractArrayRaw(payload_json, 'markets') AS market_json;
```

At first, store the ratio dictionaries raw and only derive mid-rates after inspecting real payloads from your own data. That avoids inventing assumptions too early.

## 6.8 Gold: keep the marts few and high-value

Do **not** create twenty marts. Start with these:

* `gold_currency_ref_hour`
* `gold_listing_ref_hour`
* `gold_liquidity_ref_hour`
* `gold_bulk_premium_hour`
* `gold_set_ref_hour`
* `research_backtest_runs`
* `research_backtest_results`
* `scanner_recommendations`
* `scanner_alert_log`
* `journal_events`

That is enough for a serious v1.

---

## 7. How the daemon should actually run

## 7.1 Keep one service name, refactor the internals

Keep the existing CLI/service name `market_harvester` for backwards compatibility, but internally turn it into a unified market sync daemon.

It should own:

* one OAuth token lifecycle
* one request client / rate-limit state
* one scheduler loop
* two queue types: PSAPI and CXAPI

## 7.2 No thread pool is needed

The current threaded loop is unnecessary and makes rate-limit behavior harder to reason about.

A single-threaded scheduler is enough:

```python
while True:
    now = utcnow()

    if psapi_queue.is_due(now):
        sync_psapi_once()

    if cxapi_queue.is_due(now):
        sync_cxapi_until_current_end()

    if refresh_queue.is_due(now):
        run_sql_refresh_group()

    if scanner_queue.is_due(now):
        run_enabled_strategies()
        emit_reports_and_alerts()

    sleep(next_due_delay_with_rate_limit_guard())
```

This is easier to develop, test, and maintain.

## 7.3 PSAPI sync logic

Rules:

* one queue per realm
* request documented path only
* no league parameter
* checkpoint key based on queue, not league
* write raw stash changes row-by-row
* write request log
* write checkpoint log
* refresh current-state / fast marts
* if returned `stashes` is empty and `next_change_id` has not advanced, mark queue idle and poll later ([Path of Exile][1])

For path handling:

* PC realm: `/public-stash-tabs`
* console realm: `/public-stash-tabs/<realm>`

Use the documented path shape, not undocumented query parameters. ([Path of Exile][1])

## 7.4 CXAPI sync logic

Rules:

* one queue per realm
* request documented path only
* explicit hour id always
* on cold start without checkpoint, start from `last_completed_hour - backfill_hours`
* default backfill should be small and practical, for example 168 hours
* request until caught up
* once caught up, sleep until the next hourly boundary plus a safety offset
* write raw response, request log, checkpoint log, then refresh currency refs

Important design rule: never call CXAPI without an explicit id in normal daemon mode, because the official behavior for omitted id is “first hour of history.” ([Path of Exile][1])

## 7.5 Checkpoints should come from ClickHouse

Canonical checkpoint query pattern:

```sql
SELECT argMax(next_cursor_id, retrieved_at) AS cursor
FROM poe_trade.bronze_ingest_checkpoints
WHERE queue_key = 'psapi:pc'
  AND status IN ('success', 'idle');
```

For CX:

```sql
SELECT argMax(next_cursor_id, retrieved_at) AS cursor
FROM poe_trade.bronze_ingest_checkpoints
WHERE queue_key = 'cxapi:pc'
  AND status IN ('success', 'idle');
```

That completely removes the need for file-backed checkpoints.

## 7.6 Status reporting

Keep:

* `bronze_requests`
* `bronze_ingest_checkpoints`
* `poe_ingest_status`

Recommended additions:

* `queue_key`
* nullable `league`
* explicit `feed_kind` (`psapi`, `cxapi`)

That is enough observability for a private daemon.

---

## 8. How SQL replaces “ETL”

The clean rule is:

### 8.1 Bronze to silver = materialized views

Use MVs only for one-time expensive flattening:

* raw stash change -> stash header row
* raw stash change -> item rows
* raw CX hour -> market rows

### 8.2 Silver to current state = regular views

Use regular views for:

* effective price note
* category mapping
* latest stash state
* latest item state
* latest CX hour state

### 8.3 Silver/current state to gold = scheduled SQL refreshes

Use SQL files executed by the CLI/daemon for:

* price refs
* liquidity refs
* bulk premiums
* set references
* strategy candidate tables
* backtests
* scanner recommendation tables

That is the entire transform lifecycle.

### 8.4 Rebuild philosophy

Every gold model should support one of two modes:

* **incremental refresh** over recent time windows
* **full rebuild** from silver when logic changes materially

The CLI should provide both.

Suggested commands:

```bash
poe-ledger-cli refresh gold --group refs
poe-ledger-cli refresh gold --group strategies
poe-ledger-cli rebuild silver --from 2026-03-01
poe-ledger-cli rebuild gold --all
```

### 8.5 Use ClickHouse features, not Python loops

Use these ClickHouse patterns heavily:

* `JSONExtract*`
* `JSONExtractArrayRaw`
* `arrayJoin`
* `extract` / regex functions
* `splitByChar`
* `argMax`
* `quantileTDigest` or `quantileExact`
* `countIf`, `sumIf`
* `ASOF JOIN` for attaching nearest currency reference by time
* `LowCardinality(String)`
* `DateTime64(3,'UTC')`
* ZSTD / Delta codecs

Do not build Python loops that iterate millions of item rows to compute things ClickHouse can do in one query.

---

## 9. Strategy system: no DSL, just strategy packs

The earlier DSL idea is not wrong, but it is unnecessary.

## 9.1 Strategy pack format

Use this layout:

```text
strategies/
  bulk_essence/
    strategy.toml
    discover.sql
    backtest.sql
    notes.md
  fragment_sets/
    strategy.toml
    discover.sql
    backtest.sql
    notes.md
  cluster_large_minion/
    strategy.toml
    discover.sql
    backtest.sql
    notes.md
    eval.py        # optional, only if needed
```

## 9.2 Why TOML

Use TOML because Python 3.11 already ships `tomllib`. No YAML dependency is needed.

Example `strategy.toml`:

```toml
id = "bulk_essence"
name = "Bulk Essence Premium"
enabled = true
priority = 10
latency_class = "delayed"
execution_venue = "manual_trade"
capital_tier = "bootstrap"

[minima]
expected_profit_chaos = 20
roi = 0.20
confidence = 0.65

[params]
category = "essence"
min_sample_count = 30
target_bulk_size = 20
cooldown_minutes = 180
```

## 9.3 The SQL file is the real strategy logic

`discover.sql` should do the candidate discovery.
`backtest.sql` should do historical validation.
`notes.md` explains the logic to humans.

Only advanced strategies should have `eval.py`, for example:

* corruption EV trees
* multi-step craft simulators
* graph-based cross-market arbitrage if SQL becomes awkward

## 9.4 Why this is better than a DSL

Because it is:

* easier to debug
* easier to profile
* easier for LLMs to edit safely
* easier for you to inspect
* easier to backtest directly in ClickHouse

The SQL is already self-documenting.

---

## 10. Research and intelligence that should shape the strategy roadmap

## 10.1 What the communities are actually telling you

MF Academy explicitly presents itself around mapping-for-profit guides, spreadsheets, loot filters, software tools, and mirror services. The lesson is not “copy MF Academy”; the lesson is that profitable players standardize routes, filters, tooling, and selling discipline. ([Path of Exile][7])

TFT is still structured around mirror services and large-scale trade organization. Wealthy Exile positions itself around stash value tracking, currency-per-hour, strategy tracking, and bulk trade. Mobalytics’ recent liquidation guide still points players to Wealthy Exile and TFT for stash valuation, bulk selling, and inventory organization. Bulky’s success shows that category-first bulk handling, regex map support, fragment sets, and logbook grouping are actually useful product primitives. ([forbiddentrove.com][8])

The implementable insight is simple: the biggest consistent edges are still convenience, organization, repricing, and transformation. The tool should not hunt for mythical secrets. It should formalize these repeatable advantages.

## 10.2 What current community discussions imply for strategy priority

Recent community discussion still points to:

* Currency Exchange market making in illiquid or medium-liquidity pairs
* Rog as a serious profit engine, especially in 3.28
* scarab rerolling / arbitrage
* flasks and cluster jewels as practical profit crafts
* dump-tab / liquidation discipline and bulk selling as baseline wealth multipliers ([Reddit][9])

Treat these as **strong hypotheses**, not gospel. They are the right place to begin because they align with both community practice and the data sources you now have.

## 10.3 3.28-specific bias

Because 3.28 reduced fossil availability outside Delve and removed Tujen cluster/abyss supply, the first serious strategy pack should bias toward:

* fossil / resonator tracking
* Rog valuation
* cluster jewel repricing
* low-dimensional crafts that sell broadly
* bulk convenience markets that respond to supply shocks ([Path of Exile][6])

## 10.4 The five edge families

Every strategy should belong to at least one of these:

1. **Convenience premium**
   Small stacks vs big stacks, singles vs packages, incomplete vs complete sets.

2. **Information asymmetry**
   Dump tabs, underpriced half-finished items, niche mod combinations.

3. **Transformation edge**
   Roll, craft, reroll, corrupt, assemble, split, package, bench-finish.

4. **Venue edge**
   Manual trade vs Merchant Tab vs Currency Exchange vs bulk community venue.

5. **Regime edge**
   Patch shocks, league phase, time-of-day liquidity, meta shifts.

This classification is enough. Do not over-engineer a taxonomy beyond this.

---

## 11. Strategy priority ladder

Below is the implementation order I recommend.

## 11.1 Priority 1: high-confidence, delay-friendly, mostly SQL

### Bulk convenience premium

Targets:

* essences
* fossils
* scarabs
* catalysts
* resonators
* fragments
* invitations
* maps
* logbooks
* tomes
* blueprints

Why first:

* works with delayed PSAPI
* mostly SQL
* easy to explain
* compounds from low capital

### Fragment and set assembly

Targets:

* conqueror/shaper/elder fragment sets
* emblem sets
* invitation packages
* map bundles

Why first:

* deterministic
* low parser complexity
* strongly matches convenience premium

### Flask crafting

Flasks remain one of the most repeatedly suggested “tangible” early profit crafts in community discussions, especially early when good flask outcomes sell fast. ([Reddit][10])

Why first:

* low-dimensional mod space
* cheap entry
* broad demand
* tractable in SQL plus light heuristics

### Cluster jewel crafting

Cluster jewels remain one of the most commonly cited profit crafts, especially with strong base filters and low-complexity rolling paths. Community examples still focus on specific passive-count bases, medium clusters, and low-investment alt/regal methods. ([Reddit][11])

Why first:

* strong niche demand
* easy to start with targeted bases
* good fit for PSAPI listing comps

### Map and logbook package premium

Bulky’s feature focus is telling here: 8-mod map regex support, fragment sets, and expedition logbooks are exactly the kinds of grouped convenience markets that benefit from a focused tool. ([Path of Exile][2])

Why first:

* packaging premium is real
* grouping logic is simple
* scanner output can be very actionable

## 11.2 Priority 2: medium complexity, strong upside

### Rog engine

Community discussion around the updated Rog guide argues that 3.28’s base-supply changes should increase Rog profitability, especially because Rog can still output high item-level gear under scarcer market conditions. ([Reddit][12])

Why second:

* more context-sensitive than flasks/clusters
* very good upside
* benefits from journal feedback

### Scarab reroll / vendor-loop arbitrage

A recent tracked scarab reroll writeup attributes profit to a combination of rerolling arbitrage, Faustus/liquidity, and bulk buying discounts. ([Reddit][13])

Why second:

* very strong upside
* needs more capital
* benefits from venue-aware sale logic
* better after the bulk premium and liquidity marts exist

### CX market making and cross-rate dislocations

The Currency Exchange market-making logic is sound: provide liquidity in less-liquid pairs, earn spread, and accept inventory risk. The community framing is basically textbook market making. ([Reddit][9])

Why second:

* now enabled by your new `service:cxapi`
* mostly SQL once the hourly market graph exists
* good low-attention strategy
* not live-HFT, but still meaningful

### Dump-tab and half-finished item repricing

Why second:

* great upside
* less structured
* should wait until current-state and comparator views are trustworthy

## 11.3 Priority 3: advanced, high variance, not day one

### Watcher’s Eye / high-dimensional jewel valuation

### Forbidden pair matching

### corruption EV ladders

### double-corrupt targets

### advanced influenced / fractured rare finishing

These can be excellent, but they require better comparators, more journal truth, and often more capital. Do not build them before the boring strategies are working.

---

## 12. How backtesting should work

## 12.1 SQL-first backtesting

For deterministic and semi-deterministic strategies, backtesting should be mostly SQL:

1. freeze market refs at `t0`
2. discover candidates using only data available at `t0`
3. estimate buy price at `t0`
4. apply transform assumptions
5. estimate exit value from future windows only
6. estimate fill/hold time from future listing behavior
7. store predicted vs proxy-realized outcome

## 12.2 Fill truth hierarchy

Public Stash does not expose executed fills directly. So use:

1. **disappearance heuristics** from stash/item state
2. **CX hourly history** for exchange-eligible markets
3. **your own execution journal** as the eventual source of truth

That hierarchy is enough to validate real strategies.

## 12.3 Backtest classes

Class A: commodities, packages, sets, bulk edges
Class B: flasks, clusters, Rog-like low-dimensional crafts
Class C: high-end rares, complex crafts, corruption ladders

Do not pretend Class C is as reliable as Class A before you have journal data.

---

## 13. Scanner and execution-assistant design

## 13.1 Output shape

Every recommendation should contain:

* `strategy_id`
* `league`
* `item_or_market_key`
* `why_it_fired`
* `buy_plan`
* `max_buy`
* `transform_plan`
* `exit_plan`
* `execution_venue`
* `expected_profit_chaos`
* `expected_roi`
* `expected_hold_time`
* `confidence`
* `evidence_snapshot`

This is the exact level of output the tool should produce for you.

## 13.2 Alert suppression

Without suppression the scanner will be useless.

Each strategy should support:

* enabled / disabled
* min expected profit
* min ROI
* min confidence
* min fill probability
* cooldown per fingerprint
* max alerts per run
* max capital allocation
* budget tier
* venue filter

Global suppression should dedupe repeated candidates and suppress stale or under-threshold opportunities.

## 13.3 Output modes

Two modes only.

### Delayed recommendation mode

The core mode.

This should say:

* buy X
* pay no more than Y
* do Z to it
* sell via venue V
* expected result W

### Optional browser-search mode

Keep this optional and isolated. GGG only supports documented resources, so the system should not depend on unsupported trade-site internals for core value. ([Path of Exile][3])

That means:

* core scanner output must stand on its own
* browser search URL generation can exist as a plugin if you accept fragility
* do not build the platform around it

---

## 14. CLI design

Suggested command surface:

```bash
poe-ledger-cli service --name market_harvester
poe-ledger-cli sync status
poe-ledger-cli sync psapi-once
poe-ledger-cli sync cxapi-backfill --hours 168

poe-ledger-cli refresh silver
poe-ledger-cli refresh gold --group refs
poe-ledger-cli refresh gold --group strategies

poe-ledger-cli strategy list
poe-ledger-cli strategy enable bulk_essence
poe-ledger-cli strategy disable watcher_eye_corrupt

poe-ledger-cli research backtest --strategy bulk_essence --league Mirage --days 14
poe-ledger-cli research rank --league Mirage --budget-chaos 1000

poe-ledger-cli scan once --league Mirage
poe-ledger-cli scan watch --league Mirage

poe-ledger-cli alerts list
poe-ledger-cli alerts ack --id <alert_id>

poe-ledger-cli journal buy ...
poe-ledger-cli journal sell ...
poe-ledger-cli report daily --league Mirage
```

Optional later:

```bash
poe-ledger-cli tui
```

---

## 15. Config design

The ingest config should be simplified.

### Keep

* `POE_CLICKHOUSE_*`
* `POE_OAUTH_CLIENT_ID`
* `POE_OAUTH_CLIENT_SECRET` or file
* `POE_OAUTH_SCOPE`
* `POE_API_BASE_URL`
* `POE_AUTH_BASE_URL`
* `POE_USER_AGENT`

### Replace

Old ingest settings like:

* `POE_LEAGUES`
* `POE_CHECKPOINT_DIR`
* `POE_CURSOR_DIR`
* bootstrap-until-league complexity

with:

```env
POE_REALMS=pc
POE_OAUTH_SCOPE=service:psapi service:cxapi

POE_ENABLE_PSAPI=true
POE_ENABLE_CXAPI=true

POE_PSAPI_POLL_SECONDS=30
POE_CXAPI_BACKFILL_HOURS=168
POE_CXAPI_HOUR_OFFSET_SECONDS=15

POE_REFRESH_REFS_MINUTES=5
POE_SCAN_MINUTES=5

POE_RAW_PSAPI_TTL_DAYS=21
POE_RAW_CX_TTL_DAYS=365
POE_SILVER_TTL_DAYS=90
```

If you still want default league filters for research and reports, keep those separate from ingest config.

---

## 16. Recommended code layout

```text
poe_trade/
  cli.py

  config/
    settings.py
    constants.py

  db/
    clickhouse.py
    migrations.py

  ingestion/
    oauth.py
    poe_client.py
    rate_limit.py
    scheduler.py
    sync_state.py
    psapi_sync.py
    cxapi_sync.py
    status.py

  analytics/
    refresh.py
    reports.py
    categories.py
    price_notes.py
    signatures.py

  strategy/
    registry.py
    runner.py
    backtest.py
    scoring.py
    journal.py

  sql/
    silver/
      001_ps_stash_changes.sql
      002_ps_items_raw.sql
      003_cx_markets_hour.sql
    views/
      010_ps_items_enriched.sql
      011_ps_current_stashes.sql
      012_ps_current_items.sql
      013_cx_markets_enriched.sql
    gold/
      100_currency_ref_hour.sql
      110_listing_ref_hour.sql
      120_liquidity_ref_hour.sql
      130_bulk_premium_hour.sql
      140_set_ref_hour.sql
    strategy/
      bulk_essence/
        discover.sql
        backtest.sql
      fragment_sets/
        discover.sql
        backtest.sql
      flask_basic/
        discover.sql
        backtest.sql
      cluster_basic/
        discover.sql
        backtest.sql

  strategies/
    bulk_essence/
      strategy.toml
      notes.md
    fragment_sets/
      strategy.toml
      notes.md
    flask_basic/
      strategy.toml
      notes.md
    cluster_basic/
      strategy.toml
      notes.md
```

---

## 17. Project phases

## Phase 0 — simplify and correct the repo before adding features

### Scope

* remove file-checkpoint dependence
* simplify config
* remove PSAPI league workers
* switch to documented PSAPI path handling
* remove undocumented trade metadata from the core path
* remove unused FastAPI/uvicorn if not used anywhere else
* document the actual current schema after `0018_cleanup_unused_objects.sql`

### Deliverables

* additive migrations only; do not rewrite history
* `market_harvester` refactored into a single scheduler
* `bronze_ingest_checkpoints` usable as checkpoint source
* updated `.env.example`
* updated tests

### Exit criteria

* daemon runs PSAPI for `pc` with one queue
* restart resumes from ClickHouse checkpoint
* no filesystem cursor state required
* no league param sent to PSAPI

---

## Phase 1 — add CXAPI and unified automated sync

### Scope

* add `service:cxapi` support
* add `raw_currency_exchange_hour`
* add CX checkpointing in ClickHouse
* add unified scheduler loop
* add hourly catch-up behavior

### Deliverables

* `psapi_sync.py`
* `cxapi_sync.py`
* `scheduler.py`
* bronze request/checkpoint logging for both feeds
* cx-specific tests

### Exit criteria

* daemon syncs PSAPI continuously
* daemon syncs CXAPI automatically once per completed hour
* cold start backfills last `N` hours of CX
* steady state requires no manual interaction

---

## Phase 2 — silver models and current-state views

### Scope

* create stash-change and item-row MVs
* create CX market-row MV
* add enriched/current-state views
* parse effective price notes and basic categories

### Deliverables

* `silver_ps_stash_changes`
* `silver_ps_items_raw`
* `silver_cx_markets_hour`
* `v_ps_items_enriched`
* `v_ps_current_stashes`
* `v_ps_current_items`
* `v_cx_markets_enriched`

### Exit criteria

* you can query current public items by category and league
* you can query latest completed CX markets by league and pair
* effective prices exist for common note styles
* no Python parser is required for basic commodity strategy queries

---

## Phase 3 — gold reference marts

### Scope

* currency normalization from CX
* listing reference prices from PSAPI
* liquidity and disappearance heuristics
* bulk premium estimation
* set assembly reference values

### Deliverables

* `gold_currency_ref_hour`
* `gold_listing_ref_hour`
* `gold_liquidity_ref_hour`
* `gold_bulk_premium_hour`
* `gold_set_ref_hour`

### Exit criteria

* system can answer “fair current price”
* system can answer “likely time to sell”
* system can answer “does bulk command a premium”
* system can answer “do components sum below full package value”

---

## Phase 4 — first real strategy pack

### Scope

Implement only the highest-confidence, mostly-SQL strategies:

* bulk essences
* bulk fossils
* fragment sets
* flask crafting
* cluster crafting
* map/logbook package premium

### Deliverables

For each strategy:

* `strategy.toml`
* `discover.sql`
* `backtest.sql`
* `notes.md`

### Exit criteria

* scanner can emit real recommendations
* backtests run over a chosen historical window
* recommendations rank by profit, ROI, hold time, confidence

---

## Phase 5 — journal and truth loop

### Scope

* add manual execution journal
* link recommendations to actual actions
* compute realized PnL
* compare paper results vs realized results
* optional `Client.txt` importer behind explicit user opt-in

GGG’s current third-party guidance allows log-file reading when the user is aware of what is being done with the data. ([Path of Exile][3])

### Deliverables

* `journal_events`
* `journal_positions`
* CLI commands for buy/sell/craft/corrupt/list
* realized vs predicted reports

### Exit criteria

* paper EV can be compared to real EV
* hold times and miss rates can be calibrated from your own trades

---

## Phase 6 — scanner and optional TUI

### Scope

* continuous recommendation scans
* alert suppression
* markdown / JSON / terminal outputs
* optional TUI

### Deliverables

* `scanner_recommendations`
* `scanner_alert_log`
* `scan once`
* `scan watch`
* optional `tui`

### Exit criteria

* background scanner is usable and quiet
* you can enable/disable strategies
* you can ack/mute alerts
* terminal output is enough for daily operation

---

## Phase 7 — second strategy pack

### Scope

* Rog
* scarab reroll loops
* CX market making
* dump-tab repricing
* fossil scarcity strategies

### Exit criteria

* tool supports mid-capital compounding
* CXAPI is directly informing recommendations
* research runs show which second-pack strategies deserve real allocation

---

## Phase 8 — advanced pack and hardening

### Scope

* corruption EV
* high-dimensional jewels
* advanced rare finishing
* strategy template helpers if actually needed
* performance tuning
* rebuild tooling
* retention tuning
* CI for SQL models

### Exit criteria

* hard rebuilds are reliable
* CI catches broken SQL models
* advanced strategies are gated by real confidence, not hype

---

## 18. Acceptance criteria for the whole project

The system is “done enough” when all of the following are true:

1. One daemon continuously syncs PSAPI and CXAPI with no manual intervention.
2. ClickHouse is the only persistent state store.
3. All core transforms are expressed in ClickHouse SQL.
4. Strategies are plain SQL packs with small TOML metadata, not a custom DSL.
5. The scanner tells you exactly what to buy, what to do with it, and why.
6. Backtests can be re-run over historical windows without rewriting Python transforms.
7. The execution journal closes the loop between theory and realized profit.
8. The tool remains useful even if optional browser-search generation is disabled.
9. No undocumented PoE endpoint is required for core functionality.
10. The codebase remains understandable by a new coding agent in one pass.

---

## 19. Final doctrine for coding agents

1. Keep bronze append-only.
2. Do not add Redis or Postgres.
3. Do not add a web app.
4. Do not build a generic ETL layer.
5. Do not invent a strategy DSL.
6. Use ClickHouse MVs for raw flattening, views for enriched/current state, scheduled SQL for gold tables.
7. Use ClickHouse checkpoint history as the only cursor source.
8. Use official APIs only.
9. Treat PSAPI as delayed and CXAPI as hourly historical.
10. Start with delay-friendly, mostly-SQL strategies that actually compound.

---

## 20. The most important change from the earlier plan

The earlier version was trying to design a trading platform.

This version is designing a **private ClickHouse-native trading intelligence engine**.

That difference matters.

You do not need a platform.
You need a machine that:

* synchronizes official data automatically
* builds reliable market references
* tests strategy ideas
* ranks opportunities
* outputs clear actions
* gets better as your journal grows

That is the simplest design that still has the ceiling you want.

The next most useful artifact after this document is the exact `0022+` migration set and the first four strategy packs as `strategy.toml + discover.sql + backtest.sql`.

[1]: https://www.pathofexile.com/developer/docs/reference "https://www.pathofexile.com/developer/docs/reference"
[2]: https://www.pathofexile.com/forum/view-thread/3793066 "https://www.pathofexile.com/forum/view-thread/3793066"
[3]: https://www.pathofexile.com/developer/docs "https://www.pathofexile.com/developer/docs"
[4]: https://www.pathofexile.com/developer/docs/authorization "https://www.pathofexile.com/developer/docs/authorization"
[5]: https://www.pathofexile.com/forum/view-thread/3828185 "https://www.pathofexile.com/forum/view-thread/3828185"
[6]: https://www.pathofexile.com/forum/view-thread/3913392 "https://www.pathofexile.com/forum/view-thread/3913392"
[7]: https://www.pathofexile.com/forum/view-thread/3254599/page/38 "https://www.pathofexile.com/forum/view-thread/3254599/page/38"
[8]: https://forbiddentrove.com/ "https://forbiddentrove.com/"
[9]: https://www.reddit.com/r/pathofexile/comments/1e7rcvn/currency_trading_101_market_making_illiquid_pairs/ "https://www.reddit.com/r/pathofexile/comments/1e7rcvn/currency_trading_101_market_making_illiquid_pairs/"
[10]: https://www.reddit.com/r/pathofexile/comments/1fljzz4/profit_crafting/ "https://www.reddit.com/r/pathofexile/comments/1fljzz4/profit_crafting/"
[11]: https://www.reddit.com/r/pathofexile/comments/1770cea/can_cluster_jewels_be_crafted_for_profit/ "https://www.reddit.com/r/pathofexile/comments/1770cea/can_cluster_jewels_be_crafted_for_profit/"
[12]: https://www.reddit.com/r/pathofexile/comments/1rkvllj/from_rogs_to_riches_the_complete_guide_to_rog/ "https://www.reddit.com/r/pathofexile/comments/1rkvllj/from_rogs_to_riches_the_complete_guide_to_rog/"
[13]: https://www.reddit.com/r/pathofexile/comments/1pudhsl/big_profits_from_scarab_rerolling_and_arbitrage/ "https://www.reddit.com/r/pathofexile/comments/1pudhsl/big_profits_from_scarab_rerolling_and_arbitrage/"

