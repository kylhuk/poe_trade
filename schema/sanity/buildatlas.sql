-- BuildAtlas sanity queries repurposed for the retained schema
SELECT
    service,
    count() AS request_rows,
    round(quantileExact(0.95)(response_ms), 2) AS response_ms_p95
FROM poe_trade.bronze_requests
WHERE requested_at >= now() - INTERVAL 1 DAY
GROUP BY service
ORDER BY request_rows DESC
LIMIT 10;

SELECT
    league,
    count() AS checkpoint_rows
FROM poe_trade.bronze_ingest_checkpoints
WHERE retrieved_at >= now() - INTERVAL 1 DAY
GROUP BY league
ORDER BY checkpoint_rows DESC;

SELECT
    version,
    applied_at
FROM poe_trade.poe_schema_migrations
ORDER BY applied_at DESC
LIMIT 5;
