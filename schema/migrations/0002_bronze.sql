CREATE TABLE IF NOT EXISTS poe_trade.raw_public_stash_pages (
    ingested_at DateTime64(3, 'UTC'),
    realm String,
    league String,
    stash_id String,
    checkpoint String,
    next_change_id String,
    payload_json String
) ENGINE = MergeTree()
PARTITION BY (league, toYYYYMMDD(ingested_at))
ORDER BY (league, ingested_at)
TTL ingested_at + INTERVAL 14 DAY;

CREATE TABLE IF NOT EXISTS poe_trade.raw_currency_exchange_hour (
    recorded_at DateTime64(3, 'UTC'),
    realm String,
    league String,
    hour_ts DateTime64(3, 'UTC'),
    next_change_id String,
    payload_json String
) ENGINE = MergeTree()
PARTITION BY (league, toYYYYMMDD(hour_ts))
ORDER BY (league, hour_ts)
TTL recorded_at + INTERVAL 30 DAY;

CREATE TABLE IF NOT EXISTS poe_trade.raw_account_stash_snapshot (
    snapshot_id String,
    captured_at DateTime64(3, 'UTC'),
    realm String,
    league String,
    tab_id String,
    next_change_id String,
    payload_json String
) ENGINE = MergeTree()
PARTITION BY (league, toYYYYMMDD(captured_at))
ORDER BY (league, captured_at, snapshot_id)
TTL captured_at + INTERVAL 20 DAY;
