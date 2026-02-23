-- Quick health checks for bronze ingestion tables
SELECT
    league,
    count() AS rows,
    max(ingested_at) AS latest_public_stash
FROM poe_trade.raw_public_stash_pages
GROUP BY league
ORDER BY league;

SELECT
    league,
    max(hour_ts) AS latest_exchange_hour
FROM poe_trade.raw_currency_exchange_hour
WHERE hour_ts >= now() - INTERVAL 1 DAY
GROUP BY league
ORDER BY league;

SELECT
    league,
    count() AS snapshot_rows
FROM poe_trade.raw_account_stash_snapshot
WHERE captured_at >= now() - INTERVAL 1 DAY
GROUP BY league
ORDER BY league;
