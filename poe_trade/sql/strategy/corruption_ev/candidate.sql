SELECT
    toDateTime(time_bucket) AS time_bucket,
    coalesce(league, '') AS league,
    concat(category, ':', base_type, ':', coalesce(price_currency, 'none')) AS item_or_market_key,
    concat(category, ':', base_type, ':', coalesce(price_currency, 'none')) AS semantic_key,
    coalesce(median_price_amount, 0.0) * 0.1 AS expected_profit_chaos,
    coalesce(median_price_amount, 0.0) / 10.0 AS expected_roi,
    least(1.0, toFloat64(listing_count) / 80.0) AS confidence,
    listing_count AS sample_count,
    'Corruption market spread remains favorable at current listing volume' AS why_it_fired,
    'Acquire low-entry bases with stable listing depth before vaal attempts' AS buy_plan,
    'Cycle corruption attempts while observed ROI stays above baseline' AS transform_plan,
    'Exit when corrupted-result premium compresses or depth falls below threshold' AS exit_plan,
    '3h' AS expected_hold_time,
    realm,
    category,
    base_type,
    price_currency,
    listing_count,
    median_price_amount
FROM poe_trade.gold_listing_ref_hour
WHERE category = 'other';
