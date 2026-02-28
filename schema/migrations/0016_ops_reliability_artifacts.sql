-- Reliability logging for ingestion drift, mute windows, and request telemetry

CREATE TABLE IF NOT EXISTS poe_trade.ops_drift_log (
    triggered_at DateTime64(3, 'UTC'),
    service String,
    cursor String,
    lag_seconds Float64,
    restart_action String,
    reason String,
    payload_json String,
    league Nullable(String),
    realm Nullable(String),
    endpoint Nullable(String)
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(triggered_at)
ORDER BY (service, triggered_at, cursor)
TTL triggered_at + INTERVAL 90 DAY;

CREATE TABLE IF NOT EXISTS poe_trade.ops_signal_mute_log (
    ts DateTime64(3, 'UTC'),
    signal_class String,
    mute_reason String,
    auto_resume_at Nullable(DateTime64(3, 'UTC')),
    source String,
    payload_json String,
    league Nullable(String),
    realm Nullable(String)
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(ts)
ORDER BY (signal_class, ts)
TTL ts + INTERVAL 90 DAY;

CREATE TABLE IF NOT EXISTS poe_trade.bronze_requests (
    requested_at DateTime64(3, 'UTC'),
    service String,
    realm Nullable(String),
    league Nullable(String),
    endpoint String,
    http_method String,
    status UInt16,
    attempts UInt8,
    response_ms UInt32,
    rate_limit_raw Nullable(String),
    rate_limit_parsed Nullable(String),
    retry_after_seconds Nullable(Float64),
    error Nullable(String)
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(requested_at)
ORDER BY (
    service,
    ifNull(realm, ''),
    ifNull(league, ''),
    endpoint,
    requested_at
)
TTL requested_at + INTERVAL 30 DAY;

CREATE VIEW IF NOT EXISTS poe_trade.v_slo_metrics AS
SELECT
    now() AS ts,
    greatest(
        0,
        dateDiff(
            'second',
            ifNull(latest_ingest.max_retrieved_at, now()),
            now()
        )
    ) AS ingest_latency_seconds,
    greatest(
        0,
        dateDiff(
            'second',
            ifNull(latest_alert.max_alert_ts, now()),
            now()
        )
    ) AS alert_latency_seconds
FROM (
    SELECT max(retrieved_at) AS max_retrieved_at
    FROM poe_trade.bronze_ingest_checkpoints
) AS latest_ingest
CROSS JOIN (
    SELECT max(ts) AS max_alert_ts
    FROM poe_trade.overlay_event_log
    WHERE event_name = 'alert_ack'
) AS latest_alert;

GRANT INSERT ON poe_trade.ops_drift_log TO poe_ingest_writer;
GRANT SELECT ON poe_trade.ops_drift_log TO poe_api_reader;

GRANT INSERT ON poe_trade.ops_signal_mute_log TO poe_ingest_writer;
GRANT SELECT ON poe_trade.ops_signal_mute_log TO poe_api_reader;

GRANT INSERT ON poe_trade.bronze_requests TO poe_ingest_writer;
GRANT SELECT ON poe_trade.bronze_requests TO poe_api_reader;

GRANT SELECT ON poe_trade.v_slo_metrics TO poe_api_reader;
