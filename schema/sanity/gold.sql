-- Gold layer sanity checks focused on ingestion health signals
SELECT
    realm,
    league,
    count() AS market_rows,
    max(time_bucket) AS latest_hour
FROM poe_trade.gold_currency_ref_hour
GROUP BY
    realm,
    league
ORDER BY latest_hour DESC
LIMIT 20;

SELECT
    realm,
    ifNull(league, 'unknown') AS league,
    category,
    count() AS listing_rows,
    max(time_bucket) AS latest_hour
FROM poe_trade.gold_listing_ref_hour
GROUP BY
    realm,
    league,
    category
ORDER BY latest_hour DESC
LIMIT 20;

SELECT
    realm,
    ifNull(league, 'unknown') AS league,
    category,
    listing_count,
    priced_listing_count,
    median_stack_size
FROM poe_trade.gold_liquidity_ref_hour
ORDER BY time_bucket DESC
LIMIT 20;

SELECT
    realm,
    ifNull(league, 'unknown') AS league,
    category,
    bulk_listing_count,
    small_listing_count,
    median_bulk_price_amount,
    median_small_price_amount
FROM poe_trade.gold_bulk_premium_hour
ORDER BY time_bucket DESC
LIMIT 20;

SELECT
    realm,
    ifNull(league, 'unknown') AS league,
    category,
    distinct_base_types,
    listing_count
FROM poe_trade.gold_set_ref_hour
ORDER BY time_bucket DESC
LIMIT 20;
