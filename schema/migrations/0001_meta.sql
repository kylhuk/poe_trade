CREATE DATABASE IF NOT EXISTS poe_trade;

CREATE TABLE IF NOT EXISTS poe_trade.poe_schema_migrations (
    version String,
    description String,
    checksum String,
    applied_at DateTime64(3, 'UTC')
        DEFAULT now64(3, 'UTC')
) ENGINE = ReplacingMergeTree()
ORDER BY (version)
SETTINGS index_granularity = 8192;
