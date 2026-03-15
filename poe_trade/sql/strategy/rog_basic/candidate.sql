SELECT
    toDateTime(time_bucket) AS time_bucket,
    coalesce(league, '') AS league,
    concat(category, ':', base_type, ':', coalesce(price_currency, 'none')) AS item_or_market_key,
    concat(category, ':', base_type, ':', coalesce(price_currency, 'none')) AS semantic_key,
    coalesce(median_price_amount, 0.0) * 0.09 AS expected_profit_chaos,
    coalesce(median_price_amount, 0.0) / 15.0 AS expected_roi,
    least(1.0, toFloat64(listing_count) / 90.0) AS confidence,
    listing_count AS sample_count,
    'Rog-crafted base pricing still leaves measurable manual craft upside' AS why_it_fired,
    'Buy bases with low entry cost and enough listings to support fast exits' AS buy_plan,
    'Run Rog craft attempts only while projected spread stays positive' AS transform_plan,
    'Exit when crafted-result premium no longer clears baseline ROI' AS exit_plan,
    '3h' AS expected_hold_time,
    realm,
    category,
    base_type,
    price_currency,
    listing_count,
    median_price_amount
FROM poe_trade.gold_listing_ref_hour
WHERE category = 'other';
