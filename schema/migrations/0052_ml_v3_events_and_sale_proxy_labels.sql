CREATE TABLE IF NOT EXISTS poe_trade.silver_v3_stash_snapshots (
    snapshot_ts DateTime64(3, 'UTC') CODEC(Delta(8), ZSTD(1)),
    realm LowCardinality(String),
    league LowCardinality(String),
    stash_id String CODEC(ZSTD(6)),
    account_name Nullable(String),
    stash_name Nullable(String),
    next_change_id String,
    item_identity_keys Array(String) CODEC(ZSTD(6)),
    item_count UInt32,
    inserted_at DateTime64(3, 'UTC') DEFAULT now64(3) CODEC(Delta(8), ZSTD(1))
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(snapshot_ts)
ORDER BY (league, realm, stash_id, snapshot_ts)
SETTINGS index_granularity = 8192;

CREATE MATERIALIZED VIEW IF NOT EXISTS poe_trade.mv_raw_public_stash_to_v3_stash_snapshots
TO poe_trade.silver_v3_stash_snapshots
AS
WITH
    JSONExtractArrayRaw(base.payload_json, 'items') AS items,
    ifNull(JSONExtractString(base.payload_json, 'accountName'), '') AS account_name_raw,
    ifNull(JSONExtractString(base.payload_json, 'stash'), '') AS stash_name_raw
SELECT
    base.ingested_at AS snapshot_ts,
    base.realm AS realm,
    ifNull(base.league, 'unknown') AS league,
    base.stash_id AS stash_id,
    nullIf(account_name_raw, '') AS account_name,
    nullIf(stash_name_raw, '') AS stash_name,
    base.next_change_id AS next_change_id,
    arrayMap(
        item_json -> if(
            nullIf(JSONExtractString(item_json, 'id'), '') IS NOT NULL,
            nullIf(JSONExtractString(item_json, 'id'), ''),
            lower(hex(SHA256(concat(
                ifNull(account_name_raw, ''),
                '|',
                ifNull(base.stash_id, ''),
                '|',
                ifNull(JSONExtractString(item_json, 'baseType'), ''),
                '|',
                ifNull(JSONExtractString(item_json, 'rarity'), ''),
                '|',
                toString(ifNull(JSONExtractInt(item_json, 'ilvl'), 0)),
                '|',
                ifNull(JSONExtractRaw(item_json, 'explicitMods'), '[]'),
                '|',
                ifNull(JSONExtractRaw(item_json, 'implicitMods'), '[]'),
                '|',
                ifNull(JSONExtractRaw(item_json, 'craftedMods'), '[]'),
                '|',
                ifNull(JSONExtractRaw(item_json, 'fracturedMods'), '[]'),
                '|',
                ifNull(JSONExtractRaw(item_json, 'enchantMods'), '[]')
            ))))
        ),
        items
    ) AS item_identity_keys,
    toUInt32(length(item_identity_keys)) AS item_count,
    now64(3) AS inserted_at
FROM poe_trade.raw_public_stash_pages AS base;

CREATE TABLE IF NOT EXISTS poe_trade.silver_v3_item_events (
    event_ts DateTime64(3, 'UTC') CODEC(Delta(8), ZSTD(1)),
    realm LowCardinality(String),
    league LowCardinality(String),
    stash_id String CODEC(ZSTD(6)),
    item_id Nullable(String),
    identity_key String,
    fingerprint_v3 String,
    event_type LowCardinality(String),
    previous_observed_at Nullable(DateTime64(3, 'UTC')),
    current_observed_at DateTime64(3, 'UTC'),
    previous_price_note Nullable(String),
    current_price_note Nullable(String),
    previous_parsed_amount Nullable(Float64),
    current_parsed_amount Nullable(Float64),
    event_weight Float32,
    event_payload_json String CODEC(ZSTD(6)),
    inserted_at DateTime64(3, 'UTC') DEFAULT now64(3) CODEC(Delta(8), ZSTD(1))
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(event_ts)
ORDER BY (league, realm, stash_id, identity_key, event_ts)
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS poe_trade.ml_v3_sale_proxy_labels (
    as_of_ts DateTime64(3, 'UTC') CODEC(Delta(8), ZSTD(1)),
    realm LowCardinality(String),
    league LowCardinality(String),
    stash_id String CODEC(ZSTD(6)),
    item_id Nullable(String),
    identity_key String,
    likely_sold UInt8,
    sold_probability Float32,
    label_weight Float32,
    label_source LowCardinality(String),
    time_to_exit_hours Nullable(Float32),
    sale_price_anchor_chaos Nullable(Float64),
    inserted_at DateTime64(3, 'UTC') DEFAULT now64(3) CODEC(Delta(8), ZSTD(1))
) ENGINE = ReplacingMergeTree(inserted_at)
PARTITION BY toYYYYMMDD(as_of_ts)
ORDER BY (league, realm, stash_id, identity_key, as_of_ts)
SETTINGS index_granularity = 8192;

CREATE VIEW IF NOT EXISTS poe_trade.v_v3_latest_observations AS
SELECT
    argMax(observed_at, observed_at) AS observed_at,
    realm,
    league,
    stash_id,
    identity_key,
    argMax(item_id, observed_at) AS item_id,
    argMax(base_type, observed_at) AS base_type,
    argMax(rarity, observed_at) AS rarity,
    argMax(category, observed_at) AS category,
    argMax(parsed_amount, observed_at) AS parsed_amount,
    argMax(parsed_currency, observed_at) AS parsed_currency,
    argMax(effective_price_note, observed_at) AS effective_price_note,
    max(observed_at) AS max_observed_at
FROM poe_trade.silver_v3_item_observations
GROUP BY realm, league, stash_id, identity_key;

GRANT SELECT ON poe_trade.silver_v3_stash_snapshots TO poe_api_reader;
GRANT SELECT ON poe_trade.silver_v3_item_events TO poe_api_reader;
GRANT SELECT ON poe_trade.ml_v3_sale_proxy_labels TO poe_api_reader;
GRANT SELECT ON poe_trade.v_v3_latest_observations TO poe_api_reader;
