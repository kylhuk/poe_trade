SELECT
    toDateTime(time_bucket) AS time_bucket,
    coalesce(league, '') AS league,
    concat(category, ':', base_type, ':', coalesce(price_currency, 'none')) AS item_or_market_key,
    concat(category, ':', base_type, ':', coalesce(price_currency, 'none')) AS semantic_key,
    coalesce(median_price_amount, 0.0) * 0.08 AS expected_profit_chaos,
    coalesce(median_price_amount, 0.0) / 14.0 AS expected_roi,
    least(1.0, toFloat64(listing_count) / 110.0) AS confidence,
    listing_count AS sample_count,
    'Dump-tab listings show repricing headroom with broad market coverage' AS why_it_fired,
    'Buy dump-tab undercuts where median anchor still supports quick relist' AS buy_plan,
    'Batch-reprice inventory upward while queue depth confirms demand' AS transform_plan,
    'Exit once undercut pressure rebuilds and spread returns to baseline' AS exit_plan,
    '90m' AS expected_hold_time,
    realm,
    category,
    base_type,
    price_currency,
    listing_count,
    median_price_amount
FROM poe_trade.gold_listing_ref_hour
WHERE category = 'other';
