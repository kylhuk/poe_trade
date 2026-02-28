-- Gold layer sanity checks focused on ingestion health signals
SELECT
    league,
    service,
    count() AS checkpoint_batches,
    round(avg(retry_count), 2) AS avg_retry_count
FROM poe_trade.bronze_ingest_checkpoints
WHERE retrieved_at >= now() - INTERVAL 6 HOUR
GROUP BY
    league,
    service
ORDER BY checkpoint_batches DESC
LIMIT 20;

SELECT
    league,
    count() AS trade_rows,
    quantileExact(0.5)(dateDiff('second', listing_ts, delist_ts)) AS median_listing_duration
FROM poe_trade.bronze_trade_metadata
WHERE listing_ts IS NOT NULL
GROUP BY league
ORDER BY trade_rows DESC;

SELECT
    status,
    count() AS status_rows,
    round(avg(request_rate), 2) AS avg_request_rate
FROM poe_trade.poe_ingest_status
GROUP BY status
ORDER BY status;
