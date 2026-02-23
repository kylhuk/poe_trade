-- Silver table sanity checks
SELECT
    league,
    count() AS items,
    max(captured_at) AS last_item_at
FROM poe_trade.item_canonical
GROUP BY league
ORDER BY league;

SELECT
    league,
    avg(price_chaos) AS avg_listing_price,
    max(listed_at) AS freshest_listing
FROM poe_trade.listing_canonical
WHERE listed_at >= now() - INTERVAL 1 DAY
GROUP BY league
ORDER BY league;

SELECT
    league,
    max(time_bucket) AS currency_bucket
FROM poe_trade.currency_rates
GROUP BY league
ORDER BY league;
