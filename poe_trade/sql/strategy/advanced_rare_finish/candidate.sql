SELECT
    toDateTime(time_bucket) AS time_bucket,
    coalesce(league, '') AS league,
    concat(category, ':', base_type, ':', coalesce(price_currency, 'none')) AS item_or_market_key,
    concat(category, ':', base_type, ':', coalesce(price_currency, 'none')) AS semantic_key,
    coalesce(median_price_amount, 0.0) * greatest(toFloat64(listing_count), 1.0) * 0.015 AS expected_profit_chaos,
    coalesce(median_price_amount, 0.0) / greatest(toFloat64(listing_count), 1.0) AS expected_roi,
    least(1.0, toFloat64(listing_count) / 120.0) AS confidence,
    listing_count AS sample_count,
    'Advanced rare finish listings show sustained spread and turnover pressure' AS why_it_fired,
    'Buy underpriced rare bases that still show reliable listing depth' AS buy_plan,
    'Refine suffix and prefix quality before repricing into active demand' AS transform_plan,
    'Exit when comparable rare listings compress and spread drops below baseline' AS exit_plan,
    '4h' AS expected_hold_time,
    realm,
    category,
    base_type,
    price_currency,
    listing_count,
    median_price_amount
FROM poe_trade.gold_listing_ref_hour
WHERE category = 'other';
