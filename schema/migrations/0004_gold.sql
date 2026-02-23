CREATE TABLE IF NOT EXISTS poe_trade.price_stats_1h (
    league String,
    fp_loose String,
    time_bucket DateTime64(3, 'UTC'),
    p10 Float64,
    p25 Float64,
    p50 Float64,
    p75 Float64,
    p90 Float64,
    listing_count UInt32,
    spread Float64,
    volatility Float64,
    liquidity_score Float64,
    median_price Float64,
    metadata String
) ENGINE = MergeTree()
PARTITION BY (league, toYYYYMMDD(time_bucket))
ORDER BY (league, fp_loose, time_bucket)
TTL time_bucket + INTERVAL 365 DAY;

CREATE TABLE IF NOT EXISTS poe_trade.stash_price_suggestions (
    snapshot_id String,
    item_uid String,
    league String,
    est_price_chaos Float64,
    list_price_chaos Float64,
    confidence Float64,
    reason_codes Array(String),
    created_at DateTime64(3, 'UTC'),
    updated_at DateTime64(3, 'UTC'),
    details String
) ENGINE = MergeTree()
PARTITION BY (league, toYYYYMMDD(created_at))
ORDER BY (league, snapshot_id)
TTL created_at + INTERVAL 365 DAY;

CREATE TABLE IF NOT EXISTS poe_trade.flip_opportunities (
    detected_at DateTime64(3, 'UTC'),
    league String,
    query_key String,
    buy_max Float64,
    sell_min Float64,
    expected_profit Float64,
    liquidity_score Float64,
    expiry_ts DateTime64(3, 'UTC'),
    metadata String
) ENGINE = MergeTree()
PARTITION BY (league, toYYYYMMDD(detected_at))
ORDER BY (league, detected_at, query_key)
TTL detected_at + INTERVAL 365 DAY;

CREATE TABLE IF NOT EXISTS poe_trade.craft_opportunities (
    detected_at DateTime64(3, 'UTC'),
    league String,
    item_uid String,
    plan_id String,
    craft_cost Float64,
    est_after_price Float64,
    ev Float64,
    risk_score Float64,
    details String
) ENGINE = MergeTree()
PARTITION BY (league, toYYYYMMDD(detected_at))
ORDER BY (league, detected_at, item_uid)
TTL detected_at + INTERVAL 365 DAY;

CREATE TABLE IF NOT EXISTS poe_trade.farming_sessions (
    session_id String,
    realm String,
    league String,
    start_snapshot DateTime64(3, 'UTC'),
    end_snapshot DateTime64(3, 'UTC'),
    tag String,
    duration_s UInt32,
    profit_chaos Float64,
    profit_per_hour Float64,
    notes String
) ENGINE = MergeTree()
PARTITION BY (league, toYYYYMMDD(start_snapshot))
ORDER BY (league, start_snapshot, session_id)
TTL start_snapshot + INTERVAL 365 DAY;
