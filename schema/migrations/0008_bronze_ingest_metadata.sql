CREATE TABLE IF NOT EXISTS poe_trade.bronze_ingest_checkpoints (
    service String,
    realm String,
    league String,
    endpoint String,
    last_cursor_id String,
    next_cursor_id String,
    cursor_hash String,
    retrieved_at DateTime64(3, 'UTC'),
    retry_count UInt32,
    status String,
    error String,
    http_status UInt16,
    response_ms UInt32
) ENGINE = MergeTree()
PARTITION BY (league, toYYYYMMDD(retrieved_at))
ORDER BY (service, realm, league, retrieved_at);

CREATE TABLE IF NOT EXISTS poe_trade.bronze_trade_metadata (
    retrieved_at DateTime64(3, 'UTC'),
    service String,
    realm String,
    league String,
    cursor String,
    trade_id String,
    item_id String,
    listing_ts Nullable(DateTime64(3, 'UTC')),
    delist_ts Nullable(DateTime64(3, 'UTC')),
    trade_data_hash String,
    rate_limit_raw String,
    rate_limit_parsed String,
    http_status Nullable(UInt16),
    payload_json String
) ENGINE = MergeTree()
PARTITION BY (league, toYYYYMMDD(retrieved_at))
ORDER BY (league, retrieved_at, trade_id);

CREATE VIEW IF NOT EXISTS poe_trade.v_latest_bronze_checkpoints AS
SELECT
    service,
    realm,
    league,
    endpoint,
    last_cursor_id,
    next_cursor_id,
    cursor_hash,
    retrieved_at,
    status,
    retry_count,
    http_status,
    response_ms
FROM (
    SELECT *
    FROM poe_trade.bronze_ingest_checkpoints
    ORDER BY retrieved_at DESC
    LIMIT 10
);
