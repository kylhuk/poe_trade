CREATE TABLE IF NOT EXISTS poe_trade.poe_ingest_status (
    league String,
    realm String,
    source String,
    last_cursor String,
    next_change_id String,
    last_ingest_at DateTime64(3, 'UTC'),
    request_rate Float64,
    error_count UInt32,
    stalled_since DateTime64(3, 'UTC'),
    last_error String,
    status String
) ENGINE = MergeTree()
PARTITION BY (league, toYYYYMMDD(last_ingest_at))
ORDER BY (league, realm, source, last_ingest_at)
TTL last_ingest_at + INTERVAL 90 DAY;
