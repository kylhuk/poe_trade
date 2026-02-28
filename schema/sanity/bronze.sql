-- Bronze layer health checks for the retained ingestion tables
SELECT
    league,
    count() AS rows,
    max(ingested_at) AS latest_public_stash
FROM poe_trade.raw_public_stash_pages
GROUP BY league
ORDER BY league;

SELECT
    league,
    max(captured_at) AS latest_snapshot
FROM poe_trade.raw_account_stash_snapshot
WHERE captured_at >= now() - INTERVAL 1 DAY
GROUP BY league
ORDER BY league;

SELECT
    league,
    quantileExact(0.95)(retry_count) AS retry_p95,
    max(retrieved_at) AS latest_checkpoint
FROM poe_trade.bronze_ingest_checkpoints
WHERE retrieved_at >= now() - INTERVAL 1 HOUR
GROUP BY league
ORDER BY league;

SELECT
    league,
    quantileExact(0.95)(dateDiff('second', listing_ts, now())) AS listing_age_p95
FROM poe_trade.bronze_trade_metadata
WHERE listing_ts >= now() - INTERVAL 1 HOUR
GROUP BY league
ORDER BY league;

SELECT
    league,
    service,
    count() AS request_rows,
    quantileExact(0.95)(response_ms) AS response_ms_p95
FROM poe_trade.bronze_requests
WHERE requested_at >= now() - INTERVAL 1 HOUR
GROUP BY
    league,
    service
ORDER BY request_rows DESC
LIMIT 10;

SELECT
    event_type,
    league,
    count() AS recent_events,
    max(event_ts) AS latest_event_ts
FROM poe_trade.v_ingest_events_merged
WHERE event_ts >= now() - INTERVAL 1 HOUR
GROUP BY
    event_type,
    league
ORDER BY
    event_type,
    league;

SELECT
    league,
    coalesce(status_text, 'unknown') AS status,
    count() AS status_rows,
    max(event_ts) AS last_ingest_at
FROM poe_trade.v_ingest_events_merged
WHERE event_type = 'status'
GROUP BY
    league,
    status
ORDER BY league, status;
