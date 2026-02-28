-- Record fallback drill attempts so operators can measure recovery action

CREATE TABLE IF NOT EXISTS poe_trade.fallback_drill_log (
    ts DateTime64(3, 'UTC'),
    drill_id String,
    service String,
    league Nullable(String),
    realm Nullable(String),
    scenario String,
    burst_count UInt32,
    burst_window_seconds Float64,
    retry_after_seconds Float64,
    recovery_time Float64,
    payload_json String
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(ts)
ORDER BY (ts, drill_id)
TTL ts + INTERVAL 90 DAY;

GRANT INSERT ON poe_trade.fallback_drill_log TO poe_ingest_writer;
GRANT SELECT ON poe_trade.fallback_drill_log TO poe_api_reader;
