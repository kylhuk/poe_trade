SELECT
    time_bucket,
    coalesce(league, '') AS league,
    concat(category, ':', base_type, ':', coalesce(price_currency, 'none')) AS item_or_market_key,
    concat(category, ':', base_type, ':', coalesce(price_currency, 'none')) AS semantic_key,
    coalesce(median_price_amount, 0.0) * 0.2 AS expected_profit_chaos,
    coalesce(median_price_amount, 0.0) / 8.0 AS expected_roi,
    least(1.0, toFloat64(listing_count) / 70.0) AS confidence,
    concat('high-dim jewel spread for ', base_type) AS summary
FROM poe_trade.gold_listing_ref_hour
WHERE category = 'cluster_jewel';
