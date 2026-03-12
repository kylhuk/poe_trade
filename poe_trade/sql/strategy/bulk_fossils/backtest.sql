SELECT
    time_bucket,
    coalesce(league, '') AS league,
    concat(category, ':bulk') AS item_or_market_key,
    (coalesce(median_small_price_amount, 0.0) - coalesce(median_bulk_price_amount, 0.0)) * toFloat64(bulk_threshold) AS expected_profit_chaos,
    if(coalesce(median_bulk_price_amount, 0.0) > 0.0, (coalesce(median_small_price_amount, 0.0) - coalesce(median_bulk_price_amount, 0.0)) / coalesce(median_bulk_price_amount, 0.0), 0.0) AS expected_roi,
    least(1.0, toFloat64(bulk_listing_count) / 60.0) AS confidence,
    'bulk fossil spread between bulk and small listings' AS summary
FROM poe_trade.gold_bulk_premium_hour
WHERE category = 'fossil';
