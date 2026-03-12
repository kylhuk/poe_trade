CREATE TABLE IF NOT EXISTS poe_trade.bronze_ingest_checkpoints_shadow_0022 (
    service String,
    queue_key String DEFAULT concat('psapi:', lowerUTF8(realm)),
    feed_kind LowCardinality(String) DEFAULT 'psapi',
    contract_version UInt16 DEFAULT 1,
    realm String,
    league Nullable(String),
    endpoint String,
    last_cursor_id String,
    next_cursor_id String,
    cursor_hash String,
    retrieved_at DateTime64(3, 'UTC') CODEC(Delta, ZSTD(1)),
    retry_count UInt32,
    status String,
    error String,
    http_status UInt16,
    response_ms UInt32
) ENGINE = MergeTree()
PARTITION BY (feed_kind, toYYYYMMDD(retrieved_at))
ORDER BY (service, queue_key, retrieved_at);

RENAME TABLE
    poe_trade.bronze_ingest_checkpoints TO poe_trade.bronze_ingest_checkpoints_backup_0022,
    poe_trade.bronze_ingest_checkpoints_shadow_0022 TO poe_trade.bronze_ingest_checkpoints;

INSERT INTO poe_trade.bronze_ingest_checkpoints (
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
    retry_count,
    status,
    error,
    http_status,
    response_ms
)
SELECT
    service,
    concat('psapi:', lowerUTF8(realm)) AS queue_key,
    'psapi' AS feed_kind,
    toUInt16(1) AS contract_version,
    realm,
    CAST(league AS Nullable(String)) AS league,
    endpoint,
    last_cursor_id,
    next_cursor_id,
    cursor_hash,
    retrieved_at,
    retry_count,
    status,
    error,
    http_status,
    response_ms
FROM poe_trade.bronze_ingest_checkpoints_backup_0022;

ALTER TABLE poe_trade.bronze_requests
    ADD COLUMN IF NOT EXISTS queue_key String DEFAULT concat('psapi:', lowerUTF8(ifNull(realm, '')))
    AFTER service;

ALTER TABLE poe_trade.bronze_requests
    ADD COLUMN IF NOT EXISTS feed_kind LowCardinality(String) DEFAULT 'psapi'
    AFTER queue_key;

ALTER TABLE poe_trade.bronze_requests
    ADD COLUMN IF NOT EXISTS contract_version UInt16 DEFAULT 1
    AFTER feed_kind;

CREATE TABLE IF NOT EXISTS poe_trade.poe_ingest_status_shadow_0022 (
    queue_key String DEFAULT concat('psapi:', lowerUTF8(realm)),
    feed_kind LowCardinality(String) DEFAULT 'psapi',
    contract_version UInt16 DEFAULT 1,
    league Nullable(String),
    realm String,
    source String,
    last_cursor String,
    next_change_id String,
    last_ingest_at DateTime64(3, 'UTC') CODEC(Delta, ZSTD(1)),
    request_rate Float64,
    error_count UInt32,
    stalled_since Nullable(DateTime64(3, 'UTC')),
    last_error String,
    status String
) ENGINE = MergeTree()
PARTITION BY (feed_kind, toYYYYMMDD(last_ingest_at))
ORDER BY (source, queue_key, last_ingest_at)
TTL last_ingest_at + INTERVAL 90 DAY;

RENAME TABLE
    poe_trade.poe_ingest_status TO poe_trade.poe_ingest_status_backup_0022,
    poe_trade.poe_ingest_status_shadow_0022 TO poe_trade.poe_ingest_status;

INSERT INTO poe_trade.poe_ingest_status (
    queue_key,
    feed_kind,
    contract_version,
    league,
    realm,
    source,
    last_cursor,
    next_change_id,
    last_ingest_at,
    request_rate,
    error_count,
    stalled_since,
    last_error,
    status
)
SELECT
    concat('psapi:', lowerUTF8(realm)) AS queue_key,
    'psapi' AS feed_kind,
    toUInt16(1) AS contract_version,
    CAST(league AS Nullable(String)) AS league,
    realm,
    source,
    last_cursor,
    next_change_id,
    last_ingest_at,
    request_rate,
    error_count,
    CAST(stalled_since AS Nullable(DateTime64(3, 'UTC'))) AS stalled_since,
    last_error,
    status
FROM poe_trade.poe_ingest_status_backup_0022;
