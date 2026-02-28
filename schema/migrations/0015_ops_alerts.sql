CREATE TABLE IF NOT EXISTS poe_trade.ops_alert_log (
    ts DateTime64(3, 'UTC'),
    alert_id String,
    league String,
    item_id String,
    severity String,
    ack_state String,
    source String,
    attention_minute_delta Float64,
    snooze_minutes UInt16,
    payload_json String
) ENGINE = MergeTree()
PARTITION BY (league, toYYYYMMDD(ts))
ORDER BY (alert_id, ts)
TTL ts + INTERVAL 90 DAY;

CREATE VIEW IF NOT EXISTS poe_trade.v_ops_alerts AS
SELECT
    base.*,
    ack.last_ack_state,
    ack.last_ack_at,
    ack.last_ack_source
FROM poe_trade.v_async_alerts AS base
LEFT JOIN (
    SELECT
        alert_id,
        argMax(ack_state, ts) AS last_ack_state,
        argMax(ts, ts) AS last_ack_at,
        argMax(source, ts) AS last_ack_source
    FROM poe_trade.ops_alert_log
    GROUP BY alert_id
) AS ack
    ON base.alert_id = ack.alert_id;

GRANT SELECT ON poe_trade.v_ops_alerts TO poe_api_reader;
GRANT INSERT ON poe_trade.ops_alert_log TO poe_ingest_writer;
GRANT SELECT ON poe_trade.ops_alert_log TO poe_api_reader;
