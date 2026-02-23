-- Gold layer sanity checks
SELECT
    league,
    count() AS stats_rows,
    max(time_bucket) AS latest_bucket
FROM poe_trade.price_stats_1h
GROUP BY league
ORDER BY league;

SELECT
    league,
    count() AS suggestions,
    avg(confidence) AS avg_confidence
FROM poe_trade.stash_price_suggestions
WHERE created_at >= now() - INTERVAL 1 DAY
GROUP BY league
ORDER BY league;

SELECT
    league,
    count() AS flips
FROM poe_trade.flip_opportunities
WHERE detected_at >= now() - INTERVAL 1 DAY
GROUP BY league
ORDER BY league;
