CREATE TABLE IF NOT EXISTS poe_trade.overlay_event_log (
    ts DateTime64(3, 'UTC'),
    event_name String,
    alert_id String,
    league String,
    item_id String,
    severity String,
    attention_minute_delta Float64,
    ack_state String,
    snooze_minutes UInt16,
    source String,
    payload_json String
) ENGINE = MergeTree()
PARTITION BY (league, toYYYYMMDD(ts))
ORDER BY (league, ts, alert_id)
TTL ts + INTERVAL 90 DAY;

GRANT INSERT ON poe_trade.overlay_event_log TO poe_ingest_writer;
GRANT SELECT ON poe_trade.overlay_event_log TO poe_api_reader;
