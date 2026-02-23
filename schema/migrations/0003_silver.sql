CREATE TABLE IF NOT EXISTS poe_trade.item_canonical (
    item_uid String,
    source String,
    captured_at DateTime64(3, 'UTC'),
    league String,
    base_type String,
    rarity String,
    ilvl UInt16,
    corrupted Bool,
    quality UInt8,
    sockets UInt8,
    links UInt8,
    influences Array(String),
    modifier_ids Array(String),
    modifier_tiers Array(UInt8),
    flags Array(String),
    fp_exact String,
    fp_loose String,
    payload_json String
) ENGINE = ReplacingMergeTree(fp_exact)
PARTITION BY (league, toYYYYMMDD(captured_at))
ORDER BY (league, item_uid)
TTL captured_at + INTERVAL 180 DAY;

CREATE TABLE IF NOT EXISTS poe_trade.listing_canonical (
    listing_uid String,
    item_uid String,
    listed_at DateTime64(3, 'UTC'),
    league String,
    price_amount Float64,
    price_currency String,
    price_chaos Float64,
    seller_id String,
    seller_meta String,
    last_seen_at DateTime64(3, 'UTC'),
    fp_loose String,
    payload_json String
) ENGINE = ReplacingMergeTree(listing_uid)
PARTITION BY (league, toYYYYMMDD(listed_at))
ORDER BY (league, listing_uid)
TTL listed_at + INTERVAL 180 DAY;

CREATE TABLE IF NOT EXISTS poe_trade.currency_rates (
    time_bucket DateTime64(3, 'UTC'),
    league String,
    currency String,
    chaos_rate Float64,
    volume UInt64,
    source String,
    updated_at DateTime64(3, 'UTC')
) ENGINE = ReplacingMergeTree((league, currency, time_bucket))
PARTITION BY (league, toYYYYMMDD(time_bucket))
ORDER BY (league, currency, time_bucket)
TTL time_bucket + INTERVAL 365 DAY;
