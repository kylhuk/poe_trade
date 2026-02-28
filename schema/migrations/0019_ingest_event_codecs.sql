-- 0019: optimize ingestion timestamps and unify event tracking

ALTER TABLE poe_trade.raw_public_stash_pages
MODIFY COLUMN ingested_at DateTime64(3, 'UTC') CODEC(Delta, ZSTD(1));

ALTER TABLE poe_trade.raw_account_stash_snapshot
MODIFY COLUMN captured_at DateTime64(3, 'UTC') CODEC(Delta, ZSTD(1));

ALTER TABLE poe_trade.bronze_ingest_checkpoints
MODIFY COLUMN retrieved_at DateTime64(3, 'UTC') CODEC(Delta, ZSTD(1));

ALTER TABLE poe_trade.bronze_trade_metadata
MODIFY COLUMN retrieved_at DateTime64(3, 'UTC') CODEC(Delta, ZSTD(1));

ALTER TABLE poe_trade.bronze_requests
MODIFY COLUMN requested_at DateTime64(3, 'UTC') CODEC(Delta, ZSTD(1));

CREATE VIEW IF NOT EXISTS poe_trade.v_ingest_events_merged AS
SELECT
    retrieved_at AS event_ts,
    'checkpoint' AS event_type,
    service,
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
