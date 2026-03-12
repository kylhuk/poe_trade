CREATE TABLE IF NOT EXISTS poe_trade.gold_currency_ref_hour (
    time_bucket DateTime64(0, 'UTC'),
    realm LowCardinality(String),
    league String,
    market_id String,
    base_code String,
    quote_code String,
    sample_count UInt64,
    has_lowest_ratio UInt8,
    has_highest_ratio UInt8,
    updated_at DateTime64(3, 'UTC')
) ENGINE = ReplacingMergeTree(updated_at)
PARTITION BY toYYYYMMDD(time_bucket)
ORDER BY (realm, league, market_id, time_bucket);

CREATE TABLE IF NOT EXISTS poe_trade.gold_listing_ref_hour (
    time_bucket DateTime64(0, 'UTC'),
    realm LowCardinality(String),
    league Nullable(String),
    category LowCardinality(String),
    base_type String,
    price_currency Nullable(String),
    listing_count UInt64,
    median_price_amount Nullable(Float64),
    updated_at DateTime64(3, 'UTC')
) ENGINE = ReplacingMergeTree(updated_at)
PARTITION BY toYYYYMMDD(time_bucket)
ORDER BY (realm, league, category, base_type, time_bucket);

CREATE TABLE IF NOT EXISTS poe_trade.gold_liquidity_ref_hour (
    time_bucket DateTime64(0, 'UTC'),
    realm LowCardinality(String),
    league Nullable(String),
    category LowCardinality(String),
    listing_count UInt64,
    priced_listing_count UInt64,
    median_stack_size UInt32,
    updated_at DateTime64(3, 'UTC')
) ENGINE = ReplacingMergeTree(updated_at)
PARTITION BY toYYYYMMDD(time_bucket)
ORDER BY (realm, league, category, time_bucket);

CREATE TABLE IF NOT EXISTS poe_trade.gold_bulk_premium_hour (
    time_bucket DateTime64(0, 'UTC'),
    realm LowCardinality(String),
    league Nullable(String),
    category LowCardinality(String),
    bulk_threshold UInt32,
    bulk_listing_count UInt64,
    small_listing_count UInt64,
    median_bulk_price_amount Nullable(Float64),
    median_small_price_amount Nullable(Float64),
    updated_at DateTime64(3, 'UTC')
) ENGINE = ReplacingMergeTree(updated_at)
PARTITION BY toYYYYMMDD(time_bucket)
ORDER BY (realm, league, category, time_bucket);

CREATE TABLE IF NOT EXISTS poe_trade.gold_set_ref_hour (
    time_bucket DateTime64(0, 'UTC'),
    realm LowCardinality(String),
    league Nullable(String),
    category LowCardinality(String),
    distinct_base_types UInt64,
    listing_count UInt64,
    updated_at DateTime64(3, 'UTC')
) ENGINE = ReplacingMergeTree(updated_at)
PARTITION BY toYYYYMMDD(time_bucket)
ORDER BY (realm, league, category, time_bucket);

GRANT SELECT ON poe_trade.gold_currency_ref_hour TO poe_api_reader;
GRANT SELECT ON poe_trade.gold_listing_ref_hour TO poe_api_reader;
GRANT SELECT ON poe_trade.gold_liquidity_ref_hour TO poe_api_reader;
GRANT SELECT ON poe_trade.gold_bulk_premium_hour TO poe_api_reader;
GRANT SELECT ON poe_trade.gold_set_ref_hour TO poe_api_reader;
