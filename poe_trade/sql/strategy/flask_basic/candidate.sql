SELECT
    toDateTime(time_bucket) AS time_bucket,
    coalesce(league, '') AS league,
    concat(category, ':', base_type, ':', coalesce(price_currency, 'none')) AS item_or_market_key,
    concat(category, ':', base_type, ':', coalesce(price_currency, 'none')) AS semantic_key,
    coalesce(median_price_amount, 0.0) * 0.12 AS expected_profit_chaos,
    coalesce(median_price_amount, 0.0) / 12.0 AS expected_roi,
    least(1.0, toFloat64(listing_count) / 90.0) AS confidence,
    listing_count AS sample_count,
    'Flask listings support baseline craft margin at current turnover' AS why_it_fired,
    'Acquire flask bases under median before applying high-value crafts' AS buy_plan,
    'Craft and quality-upgrade batches while listing support remains strong' AS transform_plan,
    'Exit when crafted flask premium narrows or listing depth weakens' AS exit_plan,
    '2h' AS expected_hold_time,
    realm,
    category,
    base_type,
    price_currency,
    listing_count,
    median_price_amount
FROM poe_trade.gold_listing_ref_hour
WHERE category = 'flask';
