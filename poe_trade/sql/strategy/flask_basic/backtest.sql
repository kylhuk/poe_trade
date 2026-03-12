SELECT
    time_bucket,
    coalesce(league, '') AS league,
    base_type AS item_or_market_key,
    coalesce(median_price_amount, 0.0) * 0.12 AS expected_profit_chaos,
    coalesce(median_price_amount, 0.0) / 12.0 AS expected_roi,
    least(1.0, toFloat64(listing_count) / 90.0) AS confidence,
    concat('flask craft baseline for ', base_type) AS summary
FROM poe_trade.gold_listing_ref_hour
WHERE category = 'flask';
