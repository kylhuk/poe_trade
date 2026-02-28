# ClickHouse codec plan

## Sources
- [Compression in ClickHouse](https://clickhouse.com/docs/data-compression/compression-in-clickhouse) — canonical advice to keep `ZSTD(1)` as the baseline codec, layer `Delta`/`DoubleDelta` over monotonic integers/datetimes, and only reach for `Gorilla`/`T64` when data lacks order.
- [Optimize ClickHouse codecs and compression schema](https://clickhouse.com/blog/optimize-clickhouse-codecs-compression-schema) — highlights how Delta/DoubleDelta shrink ordered sequences before `ZSTD`, giving the highest compression win for time-series/monotonic counters.

## Live schema snapshot
- Tables and engines (from `SELECT name, engine FROM system.tables WHERE database = 'poe_trade' ORDER BY name`):

```
bronze_ingest_checkpoints	MergeTree
bronze_requests	MergeTree
bronze_trade_metadata	MergeTree
poe_ingest_status	MergeTree
poe_schema_migrations	ReplacingMergeTree
raw_account_stash_snapshot	MergeTree
raw_public_stash_pages	MergeTree
```

- `SHOW CREATE TABLE` was captured for every table above, and `system.columns` reports empty `compression_codec` everywhere, which means the columns inherit the service-wide default (`ZSTD(1)`). The sections below pair that live DDL with a proposed per-column codec matrix.

## Table-by-table codec plan

### bronze_ingest_checkpoints

#### Live DDL
```
CREATE TABLE poe_trade.bronze_ingest_checkpoints
(
    `service` String,
    `realm` String,
    `league` String,
    `endpoint` String,
    `last_cursor_id` String,
    `next_cursor_id` String,
    `cursor_hash` String,
    `retrieved_at` DateTime64(3, 'UTC'),
    `retry_count` UInt32,
    `status` String,
    `error` String,
    `http_status` UInt16,
    `response_ms` UInt32
)
ENGINE = MergeTree
PARTITION BY (league, toYYYYMMDD(retrieved_at))
ORDER BY (service, realm, league, retrieved_at)
SETTINGS index_granularity = 8192
```

| Column | Type | Current codec | Proposed codec | Rationale / risk |
| --- | --- | --- | --- | --- |
| service | String | *(empty → server default `ZSTD(1)`)* | `ZSTD(1)` | Low-cardinality text; the docs recommend `ZSTD(1)` as the baseline for strings and we explicitly pin it to guard against future default changes. |
| realm | String | *(empty)* | `ZSTD(1)` | Same as `service`. |
| league | String | *(empty)* | `ZSTD(1)` | Same as `service`. |
| endpoint | String | *(empty)* | `ZSTD(1)` | Commonly repeated; `ZSTD(1)` offers strong ratio without extra CPU. |
| last_cursor_id | String | *(empty)* | `ZSTD(1)` | Cursor IDs are opaque strings, no ordering guarantee—stick with the default. |
| next_cursor_id | String | *(empty)* | `ZSTD(1)` | Same reasoning as `last_cursor_id`. |
| cursor_hash | String | *(empty)* | `ZSTD(1)` | Hashes compress well under ZSTD; no codec change needed. |
| retrieved_at | DateTime64(3, 'UTC') | *(empty)* | `CODEC(Delta, ZSTD(1))` | The ordering key already sorts by this column, so successive values are monotonic and have small deltas; per [Compression in ClickHouse](https://clickhouse.com/docs/data-compression/compression-in-clickhouse), layering `Delta` ahead of `ZSTD(1)` yields the biggest win for time columns. Expect only a modest insert-CPU bump; monitor ingestion latency and revert the codec if CPU spikes. |
| retry_count | UInt32 | *(empty)* | `ZSTD(1)` | Small integer values; default codec stays appropriate. |
| status | String | *(empty)* | `ZSTD(1)` | Event state strings compress fine with ZSTD. |
| error | String | *(empty)* | `ZSTD(1)` | Rare but long text; ZSTD handles it best. |
| http_status | UInt16 | *(empty)* | `ZSTD(1)` | Small ints benefit little from extra encodings; keep baseline. |
| response_ms | UInt32 | *(empty)* | `ZSTD(1)` | Millisecond durations are low-card/low-range, so `ZSTD(1)` is sufficient. |

### bronze_requests

#### Live DDL
```
CREATE TABLE poe_trade.bronze_requests
(
    `requested_at` DateTime64(3, 'UTC'),
    `service` String,
    `realm` Nullable(String),
    `league` Nullable(String),
    `endpoint` String,
    `http_method` String,
    `status` UInt16,
    `attempts` UInt8,
    `response_ms` UInt32,
    `rate_limit_raw` Nullable(String),
    `rate_limit_parsed` Nullable(String),
    `retry_after_seconds` Nullable(Float64),
    `error` Nullable(String)
)
ENGINE = MergeTree
PARTITION BY toYYYYMMDD(requested_at)
ORDER BY (service, ifNull(realm, ''), ifNull(league, ''), endpoint, requested_at)
TTL requested_at + toIntervalDay(30)
SETTINGS index_granularity = 8192
```

| Column | Type | Current codec | Proposed codec | Rationale / risk |
| --- | --- | --- | --- | --- |
| requested_at | DateTime64(3, 'UTC') | *(empty)* | `CODEC(Delta, ZSTD(1))` | Requests are inserted in timestamp order, so `Delta` shrinks the range before `ZSTD(1)`; aligns with [Compression in ClickHouse](https://clickhouse.com/docs/data-compression/compression-in-clickhouse) guidance for date/time sequences. |
| service | String | *(empty)* | `ZSTD(1)` | Strings stay on the default codec. |
| realm | Nullable(String) | *(empty)* | `ZSTD(1)` | Same as `service`. |
| league | Nullable(String) | *(empty)* | `ZSTD(1)` | Same as `service`. |
| endpoint | String | *(empty)* | `ZSTD(1)` | Frequent duplication benefits from ZSTD. |
| http_method | String | *(empty)* | `ZSTD(1)` | Very low cardinality; default is enough. |
| status | UInt16 | *(empty)* | `ZSTD(1)` | Small ints. |
| attempts | UInt8 | *(empty)* | `ZSTD(1)` | Bounded counter; no additional codec needed. |
| response_ms | UInt32 | *(empty)* | `ZSTD(1)` | Bounded values. |
| rate_limit_raw | Nullable(String) | *(empty)* | `ZSTD(1)` | Text payload, `ZSTD(1)` recommended baseline. |
| rate_limit_parsed | Nullable(String) | *(empty)* | `ZSTD(1)` | Same as `rate_limit_raw`. |
| retry_after_seconds | Nullable(Float64) | *(empty)* | `ZSTD(1)` | Floats mix with nulls; default keeps behavior consistent. |
| error | Nullable(String) | *(empty)* | `ZSTD(1)` | Rare error message text — `ZSTD` handles it. |

### bronze_trade_metadata

#### Live DDL
```
CREATE TABLE poe_trade.bronze_trade_metadata
(
    `retrieved_at` DateTime64(3, 'UTC'),
    `service` String,
    `realm` String,
    `league` String,
    `cursor` String,
    `trade_id` String,
    `item_id` String,
    `listing_ts` Nullable(DateTime64(3, 'UTC')),
    `delist_ts` Nullable(DateTime64(3, 'UTC')),
    `trade_data_hash` String,
    `rate_limit_raw` String,
    `rate_limit_parsed` String,
    `http_status` Nullable(UInt16),
    `payload_json` String
)
ENGINE = MergeTree
PARTITION BY (league, toYYYYMMDD(retrieved_at))
ORDER BY (league, retrieved_at, trade_id)
SETTINGS index_granularity = 8192
```

| Column | Type | Current codec | Proposed codec | Rationale / risk |
| --- | --- | --- | --- | --- |
| retrieved_at | DateTime64(3, 'UTC') | *(empty)* | `CODEC(Delta, ZSTD(1))` | Ordered by `retrieved_at`, so Delta removes predictable increments before `ZSTD(1)` per [Compression in ClickHouse](https://clickhouse.com/docs/data-compression/compression-in-clickhouse); monitor CPU on large batches. |
| service | String | *(empty)* | `ZSTD(1)` | Default; no additional compression needed. |
| realm | String | *(empty)* | `ZSTD(1)` | Default. |
| league | String | *(empty)* | `ZSTD(1)` | Default. |
| cursor | String | *(empty)* | `ZSTD(1)` | Random-looking but short. |
| trade_id | String | *(empty)* | `ZSTD(1)` | Balanced between cardinality and text, so `ZSTD(1)` is appropriate. |
| item_id | String | *(empty)* | `ZSTD(1)` | Same as `trade_id`. |
| listing_ts | Nullable(DateTime64(3, 'UTC')) | *(empty)* | `ZSTD(1)` | Not ordered by this column, so keep default. |
| delist_ts | Nullable(DateTime64(3, 'UTC')) | *(empty)* | `ZSTD(1)` | Same reason as `listing_ts`. |
| trade_data_hash | String | *(empty)* | `ZSTD(1)` | General hash text. |
| rate_limit_raw | String | *(empty)* | `ZSTD(1)` | Defaults. |
| rate_limit_parsed | String | *(empty)* | `ZSTD(1)` | Defaults. |
| http_status | Nullable(UInt16) | *(empty)* | `ZSTD(1)` | Small ints; no codec change. |
| payload_json | String | *(empty)* | `ZSTD(1)` | Large JSON might benefit from stronger ZSTD compression than LZ4; `ZSTD(1)` keeps insert cost low. |

### poe_ingest_status

#### Live DDL
```
CREATE TABLE poe_trade.poe_ingest_status
(
    `league` String,
    `realm` String,
    `source` String,
    `last_cursor` String,
    `next_change_id` String,
    `last_ingest_at` DateTime64(3, 'UTC'),
    `request_rate` Float64,
    `error_count` UInt32,
    `stalled_since` DateTime64(3, 'UTC'),
    `last_error` String,
    `status` String
)
ENGINE = MergeTree
PARTITION BY (league, toYYYYMMDD(last_ingest_at))
ORDER BY (league, realm, source, last_ingest_at)
TTL last_ingest_at + toIntervalDay(90)
SETTINGS index_granularity = 8192
```

| Column | Type | Current codec | Proposed codec | Rationale / risk |
| --- | --- | --- | --- | --- |
| league | String | *(empty)* | `ZSTD(1)` | default baseline. |
| realm | String | *(empty)* | `ZSTD(1)` | default baseline. |
| source | String | *(empty)* | `ZSTD(1)` | default baseline. |
| last_cursor | String | *(empty)* | `ZSTD(1)` | default baseline. |
| next_change_id | String | *(empty)* | `ZSTD(1)` | default baseline. |
| last_ingest_at | DateTime64(3, 'UTC') | *(empty)* | `ZSTD(1)` | Time column is not append-only (data is a status snapshot), so no additional encoding is worth the small table size; keep the default. |
| request_rate | Float64 | *(empty)* | `ZSTD(1)` | Floats behave well under ZSTD. |
| error_count | UInt32 | *(empty)* | `ZSTD(1)` | Small counter. |
| stalled_since | DateTime64(3, 'UTC') | *(empty)* | `ZSTD(1)` | Similar to `last_ingest_at` — only a few rows, so default suits. |
| last_error | String | *(empty)* | `ZSTD(1)` | Default. |
| status | String | *(empty)* | `ZSTD(1)` | Default. |

### poe_schema_migrations

#### Live DDL
```
CREATE TABLE poe_trade.poe_schema_migrations
(
    `version` String,
    `description` String,
    `checksum` String,
    `applied_at` DateTime64(3, 'UTC') DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree
ORDER BY version
SETTINGS index_granularity = 8192
```

| Column | Type | Current codec | Proposed codec | Rationale / risk |
| --- | --- | --- | --- | --- |
| version | String | *(empty)* | `ZSTD(1)` | Tiny table; default. |
| description | String | *(empty)* | `ZSTD(1)` | Default. |
| checksum | String | *(empty)* | `ZSTD(1)` | Default. |
| applied_at | DateTime64(3, 'UTC') | *(empty)* | `ZSTD(1)` | Small change-log table. |

### raw_account_stash_snapshot

#### Live DDL
```
CREATE TABLE poe_trade.raw_account_stash_snapshot
(
    `snapshot_id` String,
    `captured_at` DateTime64(3, 'UTC'),
    `realm` String,
    `league` String,
    `tab_id` String,
    `next_change_id` String,
    `payload_json` String
)
ENGINE = MergeTree
PARTITION BY (league, toYYYYMMDD(captured_at))
ORDER BY (league, captured_at, snapshot_id)
TTL captured_at + toIntervalDay(20)
SETTINGS index_granularity = 8192
```

| Column | Type | Current codec | Proposed codec | Rationale / risk |
| --- | --- | --- | --- | --- |
| snapshot_id | String | *(empty)* | `ZSTD(1)` | Default. |
| captured_at | DateTime64(3, 'UTC') | *(empty)* | `CODEC(Delta, ZSTD(1))` | Data is inserted in chronological order; applying `Delta` before `ZSTD(1)` shrinks the monotonic timestamps per [Compression in ClickHouse](https://clickhouse.com/docs/data-compression/compression-in-clickhouse). |
| realm | String | *(empty)* | `ZSTD(1)` | Default. |
| league | String | *(empty)* | `ZSTD(1)` | Default. |
| tab_id | String | *(empty)* | `ZSTD(1)` | Default. |
| next_change_id | String | *(empty)* | `ZSTD(1)` | Default. |
| payload_json | String | *(empty)* | `ZSTD(1)` | JSON benefits from `ZSTD(1)`; avoids extra CPU from higher levels. |

### raw_public_stash_pages

#### Live DDL
```
CREATE TABLE poe_trade.raw_public_stash_pages
(
    `ingested_at` DateTime64(3, 'UTC'),
    `realm` String,
    `league` String,
    `stash_id` String,
    `checkpoint` String,
    `next_change_id` String,
    `payload_json` String
)
ENGINE = MergeTree
PARTITION BY (league, toYYYYMMDD(ingested_at))
ORDER BY (league, ingested_at)
TTL ingested_at + toIntervalDay(14)
SETTINGS index_granularity = 8192
```

| Column | Type | Current codec | Proposed codec | Rationale / risk |
| --- | --- | --- | --- | --- |
| ingested_at | DateTime64(3, 'UTC') | *(empty)* | `CODEC(Delta, ZSTD(1))` | Time-ordered ingestion into this table means successive rows have small deltas; `Delta` + `ZSTD(1)` fits the [Compression in ClickHouse](https://clickhouse.com/docs/data-compression/compression-in-clickhouse) recommendation. |
| realm | String | *(empty)* | `ZSTD(1)` | Default. |
| league | String | *(empty)* | `ZSTD(1)` | Default. |
| stash_id | String | *(empty)* | `ZSTD(1)` | Default. |
| checkpoint | String | *(empty)* | `ZSTD(1)` | Default. |
| next_change_id | String | *(empty)* | `ZSTD(1)` | Default. |
| payload_json | String | *(empty)* | `ZSTD(1)` | Default. |

## Backward-compatibility & downstream notes
- These codec tweaks only change the physical encoding. No columns are renamed or relocated, so league/item naming, snapshot retention, and sampling cadence for downstream PoE tooling (market harvester, stash scribe, ops dashboards) stay untouched.
- System views and ingestion queries keep the same column types, so replaying snapshots or pointing new tooling at the tables continues to work.

## Migration safety notes
- The plan is additive: we will `ALTER TABLE <table> MODIFY COLUMN <col> TYPE <type> CODEC(...)` per column without dropping data or touching TTL/partition clauses. Every change preserves the column type and just sets an explicit codec.
- Rollback simply removes the codec clause (`ALTER TABLE ... MODIFY COLUMN ... CODEC ZSTD(1)` or omit `CODEC` altogether) and reverts to the default.
- Query impact is negligible—`ZSTD(1)` remains the decoder, and the `Delta` layer is lossless. Insertion CPU may tick up slightly for the new codecs, so stage the migration with a dry-run against clickhouse-local or a staging cluster and monitor service-level ingestion latency, then promote to prod after the instrumentation shows a tolerable CPU profile.
