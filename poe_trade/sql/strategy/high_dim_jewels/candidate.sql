SELECT
    toDateTime(time_bucket) AS time_bucket,
    coalesce(league, '') AS league,
    concat(category, ':', base_type, ':', coalesce(price_currency, 'none')) AS item_or_market_key,
    concat(category, ':', base_type, ':', coalesce(price_currency, 'none')) AS semantic_key,
    coalesce(median_price_amount, 0.0) * 0.2 AS expected_profit_chaos,
    coalesce(median_price_amount, 0.0) / 8.0 AS expected_roi,
    least(1.0, toFloat64(listing_count) / 70.0) AS confidence,
    listing_count AS sample_count,
    'High-dimensional jewel pricing dislocation remains wide in active listings' AS why_it_fired,
    'Accumulate underpriced cluster jewels where listed depth confirms signal' AS buy_plan,
    'Apply journal-backed valuation filters before committing full inventory' AS transform_plan,
    'Exit when jewel premium converges or confidence falls below target' AS exit_plan,
    '6h' AS expected_hold_time,
    realm,
    category,
    base_type,
    price_currency,
    listing_count,
    median_price_amount
FROM poe_trade.gold_listing_ref_hour
WHERE category = 'cluster_jewel';
