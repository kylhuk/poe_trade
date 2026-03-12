DROP VIEW IF EXISTS poe_trade.v_latest_bronze_checkpoints;

CREATE VIEW IF NOT EXISTS poe_trade.v_latest_bronze_checkpoints AS
SELECT
    service,
    queue_key,
    feed_kind,
    contract_version,
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

DROP VIEW IF EXISTS poe_trade.v_ingest_events_merged;

CREATE VIEW IF NOT EXISTS poe_trade.v_ingest_events_merged AS
SELECT
    retrieved_at AS event_ts,
    'checkpoint' AS event_type,
    service,
    queue_key,
    feed_kind,
    contract_version,
    realm,
    league,
    endpoint,
    status AS status_text,
    CAST(NULL AS Nullable(UInt16)) AS status_code,
    cursor_hash,
    response_ms,
    CAST(error AS Nullable(String)) AS error
FROM poe_trade.bronze_ingest_checkpoints
UNION ALL
SELECT
    requested_at AS event_ts,
    'request' AS event_type,
    service,
    queue_key,
    feed_kind,
    contract_version,
    realm,
    league,
    endpoint,
    CAST(NULL AS Nullable(String)) AS status_text,
    status AS status_code,
    CAST(NULL AS Nullable(String)) AS cursor_hash,
    response_ms,
    error
FROM poe_trade.bronze_requests
UNION ALL
SELECT
    last_ingest_at AS event_ts,
    'status' AS event_type,
    source AS service,
    queue_key,
    feed_kind,
    contract_version,
    realm,
    league,
    CAST(NULL AS Nullable(String)) AS endpoint,
    status AS status_text,
    CAST(NULL AS Nullable(UInt16)) AS status_code,
    CAST(NULL AS Nullable(String)) AS cursor_hash,
    CAST(NULL AS Nullable(UInt32)) AS response_ms,
    last_error AS error
FROM poe_trade.poe_ingest_status
WHERE last_ingest_at IS NOT NULL;

DROP VIEW IF EXISTS poe_trade.v_ops_ingest_health;

CREATE VIEW IF NOT EXISTS poe_trade.v_ops_ingest_health AS
SELECT
    service,
    queue_key,
    feed_kind,
    contract_version,
    realm,
    league,
    endpoint,
    last_checkpoint_at,
    lag_seconds,
    CASE
        WHEN lag_seconds > 60 THEN 'red'
        WHEN lag_seconds > 20 THEN 'amber'
        ELSE 'green'
    END AS severity,
    if(lag_seconds > 20, 1, 0) AS divines_per_attention_minute_risk_flag
FROM (
    SELECT
        service,
        queue_key,
        feed_kind,
        contract_version,
        realm,
        league,
        endpoint,
        max(retrieved_at) AS last_checkpoint_at,
        greatest(0, dateDiff('second', max(retrieved_at), now())) AS lag_seconds
    FROM poe_trade.bronze_ingest_checkpoints
    GROUP BY
        service,
        queue_key,
        feed_kind,
        contract_version,
        realm,
        league,
        endpoint
) AS latest_checkpoints;

GRANT SELECT ON poe_trade.v_ops_ingest_health TO poe_api_reader;
