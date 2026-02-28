-- Silver layer sanity checks re-targeted to the retained ingestion tables
SELECT
    league,
    count() AS total_trades,
    max(retrieved_at) AS most_recent_ingest
FROM poe_trade.bronze_trade_metadata
GROUP BY league
ORDER BY league;

SELECT
    league,
    countIf(listing_ts >= now() - INTERVAL 1 HOUR) AS recent_listings,
    round(countIf(listing_ts >= now() - INTERVAL 1 HOUR) * 100.0 / greatest(count(), 1), 2)
        AS recent_listing_pct
FROM poe_trade.bronze_trade_metadata
GROUP BY league
ORDER BY recent_listing_pct DESC;

SELECT
    service,
    league,
    count() AS requests_last_hour,
    quantileExact(0.95)(response_ms) AS response_ms_p95
FROM poe_trade.bronze_requests
WHERE requested_at >= now() - INTERVAL 1 HOUR
GROUP BY
    service,
    league
ORDER BY requests_last_hour DESC;
