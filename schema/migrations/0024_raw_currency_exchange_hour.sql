CREATE TABLE IF NOT EXISTS poe_trade.raw_currency_exchange_hour (
    recorded_at DateTime64(3, 'UTC') CODEC(Delta, ZSTD(1)),
    realm LowCardinality(String),
    requested_hour DateTime64(0, 'UTC') CODEC(Delta, ZSTD(1)),
    next_change_id UInt64,
    payload_json String CODEC(ZSTD(6))
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(requested_hour)
ORDER BY (realm, requested_hour)
TTL recorded_at + INTERVAL 365 DAY;

GRANT INSERT ON poe_trade.raw_currency_exchange_hour TO poe_ingest_writer;
GRANT SELECT ON poe_trade.raw_currency_exchange_hour TO poe_api_reader;
